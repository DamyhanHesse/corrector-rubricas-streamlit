import os
import time
import io
import re
from datetime import datetime
import pandas as pd
import streamlit as st

# SDK Oficial google-genai
from google import genai
from google.genai import types
from google.genai.errors import APIError

# Librerías para generación de PDF en ReportLab
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# -----------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA Y CSS CORPORATIVO (MOBILE-FIRST)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="EduEvalua AI - Evaluación Institucional",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    /* Reset y tipografía global */
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Inter', sans-serif;
        background-color: #F8FAFC;
        color: #0F172A;
    }
    
    /* Eliminar padding superior nativo de Streamlit para que el header pegue arriba */
    .block-container {
        padding-top: 0rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 1200px;
    }

    /* Ocultar elementos de Streamlit por defecto */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}

    /* Navbar Corporativo (Reemplaza al hero gigante) */
    .navbar {
        background-color: #0A2540;
        padding: 1rem 2rem;
        margin-left: -1rem;
        margin-right: -1rem;
        margin-bottom: 2rem;
        border-bottom: 4px solid #2563EB;
        display: flex;
        flex-direction: column;
    }
    .navbar-title {
        color: #FFFFFF;
        font-size: 1.5rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin: 0;
    }
    .navbar-subtitle {
        color: #94A3B8;
        font-size: 0.85rem;
        margin-top: 0.2rem;
    }

    /* Contenedores de Paneles (Tarjetas) */
    div[data-testid="stColumn"] {
        background-color: #FFFFFF;
        padding: 1.5rem !important;
        border-radius: 8px !important;
        border: 1px solid #E2E8F0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }

    /* Forzar visibilidad de las etiquetas (Labels) en fondos blancos */
    div[data-testid="stWidgetLabel"] p, label p {
        color: #1E293B !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
    }

    /* Inputs y Formularios */
    input, textarea {
        background-color: #FFFFFF !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 4px !important;
        color: #0F172A !important;
        padding: 0.6rem !important;
    }
    input:focus, textarea:focus {
        border-color: #2563EB !important;
        box-shadow: 0 0 0 1px #2563EB !important;
    }
    
    /* Botón Primario Corporativo */
    div[data-testid="stButton"] button {
        background-color: #0A2540 !important;
        color: white !important;
        border: none !important;
        border-radius: 4px !important;
        font-weight: 600 !important;
        padding: 0.75rem 1.5rem !important;
        transition: background-color 0.2s ease;
    }
    div[data-testid="stButton"] button:hover {
        background-color: #2563EB !important;
    }

    /* Títulos internos de sección */
    .section-title {
        font-size: 1.2rem;
        font-weight: 700;
        color: #0A2540;
        margin-bottom: 1.5rem;
        border-bottom: 1px solid #E2E8F0;
        padding-bottom: 0.5rem;
    }

    /* Tarjetas de Resultados */
    .result-metric {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-left: 4px solid #2563EB;
        border-radius: 4px;
        padding: 1rem;
        text-align: left;
        margin-bottom: 1rem;
    }
    .result-value {
        font-size: 2rem;
        font-weight: 700;
        color: #0A2540;
        line-height: 1;
    }
    .result-label {
        font-size: 0.75rem;
        text-transform: uppercase;
        color: #64748B;
        font-weight: 600;
        margin-top: 0.25rem;
        letter-spacing: 0.05em;
    }
    </style>
""", unsafe_allow_html=True)

CSV_FILE = "registro_calificaciones.csv"

# -----------------------------------------------------------------------------
# 2. LÓGICA DE BACKEND (Gemini, ReportLab, Pandas)
# -----------------------------------------------------------------------------
def get_gemini_client():
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        st.error("Error de configuración: GEMINI_API_KEY no encontrada.")
        st.stop()
    return genai.Client(api_key=api_key)

def generar_evaluacion_con_reintentos(client, contents, prompt_sistema, max_retries=3):
    model_id = "gemini-2.5-flash"
    for intento in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=prompt_sistema,
                    temperature=0.2
                )
            )
            return response.text
        except APIError as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                if intento < max_retries - 1:
                    time.sleep((intento + 1) * 2)
                    continue
                return None
            elif "503" in str(e):
                if intento < max_retries - 1:
                    time.sleep(2)
                    continue
                return None
            return None
        except Exception:
            return None
    return None

def cargar_registro():
    if os.path.exists(CSV_FILE):
        try:
            return pd.read_csv(CSV_FILE, on_bad_lines='skip')
        except Exception:
            return pd.DataFrame(columns=["Docente", "Estudiante", "Puntaje", "Nota", "Fecha"])
    return pd.DataFrame(columns=["Docente", "Estudiante", "Puntaje", "Nota", "Fecha"])

def guardar_registro(df):
    df.to_csv(CSV_FILE, index=False)

def generar_pdf_informe(nombre_docente, nombre_estudiante, nota, puntaje, feedback_texto):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40,
        title=f"Informe Oficial - {nombre_estudiante}"
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=14, textColor=colors.HexColor('#0A2540'), spaceAfter=15)
    body_style = ParagraphStyle('DocBody', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor('#1E293B'), spaceAfter=8)

    story = [Paragraph("INFORME DE EVALUACIÓN INSTITUCIONAL", title_style), Spacer(1, 10)]
    data = [
        [Paragraph("<b>Profesor/a Evaluador:</b>", body_style), Paragraph(nombre_docente or "No especificado", body_style)],
        [Paragraph("<b>Alumno/a:</b>", body_style), Paragraph(nombre_estudiante or "No especificado", body_style)],
        [Paragraph("<b>Puntaje Obtenido:</b>", body_style), Paragraph(str(puntaje), body_style)],
        [Paragraph("<b>Calificación Final:</b>", body_style), Paragraph(str(nota), body_style)]
    ]
    
    t = Table(data, colWidths=[130, 390])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    
    story.append(t)
    story.append(Spacer(1, 15))
    story.append(Paragraph("<b>Detalle de Retroalimentación:</b>", body_style))
    story.append(Spacer(1, 5))
    
    for linea in feedback_texto.split('\n'):
        if linea.strip():
            story.append(Paragraph(linea.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), body_style))
        else:
            story.append(Spacer(1, 4))
            
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def extraer_metrica(patron, texto):
    match = re.search(patron, texto, re.IGNORECASE)
    return match.group(1).strip() if match else "N/A"

# -----------------------------------------------------------------------------
# 3. INTERFAZ FRONT-END PRINCIPAL
# -----------------------------------------------------------------------------
def main():
    # Navbar superior estricto (Mobile-First)
    st.markdown("""
        <div class="navbar">
            <div class="navbar-title">EDUEVALUA AI</div>
            <div class="navbar-subtitle">Plataforma Operativa de Corrección Institucional</div>
        </div>
    """, unsafe_allow_html=True)

    col_form, col_results = st.columns([1, 1], gap="large")

    with col_form:
        st.markdown("<div class='section-title'>Panel de Evaluación</div>", unsafe_allow_html=True)
        
        # Etiquetas claras e inputs limpios
        profesor = st.text_input("Profesor/a:", key="prof_input")
        estudiante = st.text_input("Alumno/a:", key="est_input")

        st.markdown("<br>", unsafe_allow_html=True)
        
        opcion_rubrica = st.radio("1. Rúbrica de Evaluación", ["Texto", "Archivo (PDF/IMG)"], horizontal=True)
        rubrica_parts = []
        if opcion_rubrica == "Texto":
            rubrica_texto = st.text_area("Ingrese los criterios de evaluación", height=100, label_visibility="collapsed")
            if rubrica_texto.strip():
                rubrica_parts.append(f"--- RÚBRICA ---\n{rubrica_texto}")
        else:
            rubrica_file = st.file_uploader("Documento de rúbrica", type=["pdf", "png", "jpg"], key="rubrica_file")
            if rubrica_file:
                rubrica_parts.append(types.Part.from_bytes(data=rubrica_file.read(), mime_type=rubrica_file.type))
                rubrica_parts.append("Este archivo es la rúbrica de evaluación.")

        st.markdown("<br>", unsafe_allow_html=True)
        
        opcion_trabajo = st.radio("2. Evidencia del Alumno", ["Texto", "Archivo (PDF/IMG)"], horizontal=True)
        trabajo_parts = []
        if opcion_trabajo == "Texto":
            trabajo_texto = st.text_area("Ingrese el contenido a evaluar", height=120, label_visibility="collapsed")
            if trabajo_texto.strip():
                trabajo_parts.append(f"--- TRABAJO ---\n{trabajo_texto}")
        else:
            trabajo_file = st.file_uploader("Trabajo del estudiante", type=["pdf", "png", "jpg"], key="trabajo_file")
            if trabajo_file:
                trabajo_parts.append(types.Part.from_bytes(data=trabajo_file.read(), mime_type=trabajo_file.type))
                trabajo_parts.append("Este archivo es el trabajo del estudiante.")

        st.markdown("<br>", unsafe_allow_html=True)
        btn_evaluar = st.button("Ejecutar Análisis", use_container_width=True)

    with col_results:
        st.markdown("<div class='section-title'>Resultados</div>", unsafe_allow_html=True)
        
        if btn_evaluar:
            if not rubrica_parts or not trabajo_parts:
                st.error("Error: Se requiere la rúbrica y la evidencia del alumno para proceder.")
                return

            client = get_gemini_client()
            prompt_sistema = """
Evalúa el trabajo del estudiante contrastándolo únicamente con la rúbrica.
Responde SIEMPRE con el siguiente formato exacto al inicio:
[PUNTAJE_OBTENIDO]: <valor numérico>
[NOTA_FINAL]: <nota final>

Luego, redacta un informe estructurado:
1. Resumen Ejecutivo.
2. Desglose por criterio.
3. Fortalezas.
4. Oportunidades de mejora.
Usa lenguaje técnico y corporativo.
            """.strip()

            with st.spinner("Procesando evaluación..."):
                resultado = generar_evaluacion_con_reintentos(client, rubrica_parts + trabajo_parts, prompt_sistema)

            if resultado:
                puntaje = extraer_metrica(r'\[PUNTAJE_OBTENIDO\]:\s*(.*)', resultado)
                nota = extraer_metrica(r'\[NOTA_FINAL\]:\s*(.*)', resultado)
                feedback_limpio = re.sub(r'\[(PUNTAJE_OBTENIDO|NOTA_FINAL)\]:.*', '', resultado).strip()

                st.session_state["eval_data"] = {
                    "docente": profesor, "estudiante": estudiante,
                    "puntaje": puntaje, "nota": nota, "feedback": feedback_limpio
                }

                df_actual = cargar_registro()
                nueva_fila = pd.DataFrame([{
                    "Docente": profesor or "No especificado", "Estudiante": estudiante or "No especificado",
                    "Puntaje": puntaje, "Nota": nota, "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
                }])
                df_actual = pd.concat([df_actual, nueva_fila], ignore_index=True)
                guardar_registro(df_actual)

        if "eval_data" in st.session_state:
            data = st.session_state["eval_data"]
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"<div class='result-metric'><div class='result-value'>{data['puntaje']}</div><div class='result-label'>Puntaje</div></div>", unsafe_allow_html=True)
            with c2:
                st.markdown(f"<div class='result-metric'><div class='result-value'>{data['nota']}</div><div class='result-label'>Nota Final</div></div>", unsafe_allow_html=True)

            st.markdown(f"<div style='background: #FFFFFF; padding: 1rem; border-radius: 4px; border: 1px solid #E2E8F0; font-size: 0.9rem;'>{data['feedback'].replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            pdf_bytes = generar_pdf_informe(data["docente"], data["estudiante"], data["nota"], data["puntaje"], data["feedback"])
            st.download_button(label="Descargar PDF Oficial", data=pdf_bytes, file_name="informe_evaluacion.pdf", mime="application/pdf", use_container_width=True)
        else:
            st.markdown("<div style='text-align: center; color: #94A3B8; padding: 2rem 0; font-size: 0.9rem;'>Esperando parámetros de evaluación...</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()