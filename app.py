import streamlit as st
import sqlite3
import pandas as pd
import os
import re
import calendar
import io
from datetime import date

# Configuração inicial
st.set_page_config(page_title="Foco Usina - Gestão", layout="wide")

# --- FUNÇÕES ---
def safe_str(val):
    if pd.isna(val) or str(val).strip().upper() == 'NAN': return ""
    texto = str(val).strip()
    if texto.endswith('.0'): texto = texto[:-2]
    return texto

def formatar_cpf(texto):
    texto_limpo = safe_str(texto)
    if not texto_limpo: return ""
    num = re.sub(r'\D', '', texto_limpo)
    if len(num) == 11: return f"{num[:3]}.{num[3:6]}.{num[6:9]}-{num[9:]}"
    return texto_limpo

def formatar_telefone(texto):
    texto_limpo = safe_str(texto)
    if not texto_limpo: return ""
    num = re.sub(r'\D', '', texto_limpo)
    if len(num) == 11: return f"({num[:2]}) {num[2:7]}-{num[7:]}"
    elif len(num) == 10: return f"({num[:2]}) {num[2:6]}-{num[6:]}"
    return texto_limpo

def extrair_serie(nome_turma):
    match = re.search(r'(\d+)º', str(nome_turma))
    return f"{match.group(1)}º Ano" if match else "Outras"

def ordenar_turmas(lista_turmas):
    def chave_ordem(nome):
        dias_map = {'SEG':1, 'TER':2, 'QUA':3, 'QUI':4, 'SEX':5, 'SAB':6, 'DOM':7}
        dia_val = 8
        for sigla, num in dias_map.items():
            if sigla in str(nome).upper():
                dia_val = num
                break
        match = re.search(r'(\d{1,2})[hH:]', str(nome))
        hora_val = int(match.group(1)) if match else 24
        match_sartre = re.search(r'(\d+)º\s*(\d+)', str(nome))
        if match_sartre: return (0, int(match_sartre.group(1)), int(match_sartre.group(2)), str(nome))
        return (dia_val, hora_val, str(nome))
    return sorted(list(set([str(t) for t in lista_turmas if pd.notna(t) and safe_str(t) != ""])), key=chave_ordem)

# --- BASE DE DADOS (SUPABASE / LOCAL HÍBRIDO) ---
try:
    db_url = st.secrets["DATABASE_URL"]
    import psycopg2
    conn = psycopg2.connect(db_url, sslmode='require')
    is_postgres = True
except:
    conn = sqlite3.connect('banco.db', check_same_thread=False)
    is_postgres = False

c = conn.cursor()

# Se estiver no Supabase e estiver vazio, podemos garantir as tabelas base
if is_postgres:
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, login TEXT UNIQUE, senha TEXT, perfil TEXT, nome_professor TEXT)")
    cur.execute("SELECT COUNT(*) FROM usuarios")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO usuarios (login, senha, perfil, nome_professor) VALUES ('admin', '1234', 'admin', '') ON CONFLICT DO NOTHING")
        conn.commit()

# --- MOTOR DE ESTADO E LOGIN ---
if 'logado' not in st.session_state:
    st.session_state['logado'] = False
    st.session_state['usuario'] = None
    st.session_state['perfil'] = None
    st.session_state['nome_prof'] = None

for key in ['key_escola', 'key_turma', 'key_matricula', 'key_prof', 'key_user']:
    if key not in st.session_state: st.session_state[key] = 0

if not st.session_state['logado']:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        if os.path.exists("FOCO USINA DE ARTES.png"): st.image("FOCO USINA DE ARTES.png", use_container_width=True)
        st.markdown("<h2 style='text-align: center;'>Acesso ao Sistema</h2>", unsafe_allow_html=True)
        
        with st.form("form_login"):
            usuario_input = st.text_input("Usuário")
            senha_input = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                if is_postgres:
                    cur = conn.cursor()
                    cur.execute("SELECT login, perfil, nome_professor FROM usuarios WHERE login=%s AND senha=%s", (usuario_input, senha_input))
                    resultado = cur.fetchone()
                else:
                    c.execute("SELECT login, perfil, nome_professor FROM usuarios WHERE login=? AND senha=?", (usuario_input, senha_input))
                    resultado = c.fetchone()
                
                if resultado:
                    st.session_state['logado'] = True
                    st.session_state['usuario'] = resultado[0]
                    st.session_state['perfil'] = resultado[1]
                    st.session_state['nome_prof'] = resultado[2]
                    st.rerun()
                else:
                    st.error("⚠️ Usuário ou senha incorretos.")
    st.stop()

if os.path.exists("FOCO USINA DE ARTES.png"): st.sidebar.image("FOCO USINA DE ARTES.png", use_container_width=True)
else: st.sidebar.title("🎭 Foco Usina")

st.sidebar.markdown(f"👤 **Logado como:** {st.session_state['usuario'].title()} ({st.session_state['perfil']})")
if st.sidebar.button("Sair / Logout"):
    st.session_state['logado'] = False
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### 📁 Bloco de Trabalho")
projeto_atual = st.sidebar.radio("Selecione o Projeto:", ["Curso Extra", "Projeto de Teatro Sartre", "Turno Integral Sartre"])
st.sidebar.markdown("---")

if st.session_state['perfil'] == 'admin':
    opcoes_menu = ["Dashboard", "Escolas, Turmas, Profs e Acessos", "Cadastrar Aluno / Matrícula", "Ver / Editar Alunos", "Caderneta / Presença"]
    if projeto_atual == "Curso Extra": opcoes_menu.append("Financeiro / Extrato")
    opcoes_menu.append("Meu Perfil / Senha")
else:
    opcoes_menu = ["Dashboard", "Caderneta / Presença", "Meu Perfil / Senha"]

menu = st.sidebar.radio("Navegação", opcoes_menu)

def ler_sql(query, params=None):
    return pd.read_sql_query(query, conn, params=params)

df_escolas_db = ler_sql("SELECT nome_escola FROM escolas WHERE projeto=%s ORDER BY nome_escola" if is_postgres else "SELECT nome_escola FROM escolas WHERE projeto=? ORDER BY nome_escola", params=(projeto_atual,))
lista_escolas_limpa = [safe_str(x) for x in df_escolas_db['nome_escola'].tolist() if safe_str(x) != ""]
df_prof_db = ler_sql("SELECT nome_professor FROM professores WHERE projeto=%s ORDER BY nome_professor" if is_postgres else "SELECT nome_professor FROM professores WHERE projeto=? ORDER BY nome_professor", params=(projeto_atual,))
lista_profs = [safe_str(x) for x in df_prof_db['nome_professor'].tolist() if safe_str(x) != ""]

# --- ECRÃS DO SISTEMA ---
if menu == "Dashboard":
    st.title("Visão Geral")
    st.write(f"Bem-vindo ao sistema da Foco Usina de Artes, **{st.session_state['usuario'].title()}**.")
    st.info(f"📌 Você está no ambiente: **{projeto_atual}**.")

elif menu == "Meu Perfil / Senha":
    st.title("👤 Meu Perfil")
    st.write("Altere a sua senha de acesso ao sistema.")
    with st.form("form_senha"):
        nova_senha = st.text_input("Nova Senha", type="password")
        confirma_senha = st.text_input("Confirme a Nova Senha", type="password")
        if st.form_submit_button("Atualizar Senha", type="primary"):
            if nova_senha and nova_senha == confirma_senha:
                cur = conn.cursor()
                if is_postgres:
                    cur.execute("UPDATE usuarios SET senha=%s WHERE login=%s", (nova_senha, st.session_state['usuario']))
                else:
                    cur.execute("UPDATE usuarios SET senha=? WHERE login=?", (nova_senha, st.session_state['usuario']))
                conn.commit()
                st.success("✅ A sua senha foi alterada com sucesso!")
            else:
                st.error("⚠️ As senhas não coincidem ou estão vazias.")

elif menu == "Caderneta / Presença":
    st.title(f"📝 Caderneta Digital: {projeto_atual}")
    st.info(f"📌 Visualizando caderneta para: {projeto_atual}")
