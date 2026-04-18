import streamlit as st
import pandas as pd
from pdfminer.high_level import extract_text
import re
import zipfile
import io
from fpdf import FPDF
from datetime import datetime

# --- CONFIGURAÇÃO DE SEGURANÇA ---
SENHA_ACESSO = "MD2026"

def check_password():
    if "auth" not in st.session_state:
        st.session_state["auth"] = False
    
    if not st.session_state["auth"]:
        st.title("🏛️ Acesso Restrito - Fair Value")
        st.write("Bem-vindo ao sistema de rateio. Por favor, identifique-se.")
        senha = st.text_input("Digite a senha do escritório:", type="password")
        if st.button("Acessar Sistema"):
            if senha == SENHA_ACESSO:
                st.session_state["auth"] = True
                st.rerun()
            else:
                st.error("Senha incorreta! Verifique com o administrador.")
        return False
    return True

# --- MOTOR DE EXTRAÇÃO DE ALTA PRECISÃO V8 ---
def extrair_dados_especificos(f_binario):
    try:
        texto = extract_text(f_binario)
        texto_limpo = " ".join(texto.split())
        info = {"NF": "S/N", "V": 0.0, "Desc": "", "Data": "01/01/2026"}
        
        # 1. Número da NF
        nf_m = re.search(r"Número da NFS-e\s*(\d+)", texto_limpo)
        if nf_m: info["NF"] = nf_m.group(1)

        # 2. Data de Emissão (Abaixo da variável específica)
        termo_data = "Data e Hora da emissão da NFS-e"
        if termo_data in texto_limpo:
            pos_data = texto_limpo.find(termo_data) + len(termo_data)
            data_m = re.search(r"(\d{2}/\d{2}/\d{4})", texto_limpo[pos_data:])
            if data_m: info["Data"] = data_m.group(1)

        # 3. Descrição Integral
        if "Descrição do Serviço" in texto_limpo:
            inicio = texto_limpo.find("Descrição do Serviço") + len("Descrição do Serviço")
            fim_idx = texto_limpo.upper().find("TRIBUTAÇÃO", inicio)
            if fim_idx == -1: fim_idx = len(texto_limpo)
            info["Desc"] = texto_limpo[inicio:fim_idx].strip()

        # 4. Valor do Serviço
        val_m = re.search(r"Valor do Serviço\s*R\$\s*([\d.,]+)", texto_limpo)
        if val_m: info["V"] = float(val_m.group(1).replace(".", "").replace(",", "."))
            
        return info
    except: return None

def sugerir_nome(desc):
    match = re.search(r"(?:DRA\.|DR\.|PELA|PELO)\s+([A-ZÀ-Ú]+(?:\s+[A-ZÀ-Ú]+)?)", desc.upper())
    if match:
        n = match.group(1).strip()
        for s in [" NO ", " PELO ", " PELA ", " PERIODO", " REFERENTE"]: n = n.replace(s, "")
        return n.strip()
    return ""

def fmt(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- INTERFACE E LÓGICA ---
if check_password():
    st.set_page_config(page_title="Fair Value - Sistema de Rateio", layout="wide")
    st.title("🏛️ Fair Value - Painel de Rateio DAS")
    
    st.sidebar.image("LOGO_VERT_BLACK@4x.png", use_container_width=True)
    st.sidebar.markdown("---")
    st.sidebar.write("Organização e Precisão Contábil")

    c1, c2 = st.columns(2)
    with c1: arq_das_in = st.file_uploader("1. Guia DAS (PDF)", type=["pdf"])
    with c2: arqs_nfs_in = st.file_uploader("2. Notas Fiscais (ZIP ou PDF)", type=["zip", "pdf"], accept_multiple_files=True)

    if arq_das_in and arqs_nfs_in:
        nfs_finais = []
        for item in arqs_nfs_in:
            if item.name.lower().endswith('.zip'):
                with zipfile.ZipFile(item) as z:
                    for nome_f in z.namelist():