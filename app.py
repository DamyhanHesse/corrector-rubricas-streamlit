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
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS VISUALES
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="EduEvalua AI - Corrector Profesional",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Inter', sans-serif;
        background-color: #0F172A;
        color: #F8FAFC;
    }
    
    h1 {
        font-weight: 700 !important;
        color: #FFFFFF !important;
        letter-spacing: -0.02em;
    }
    h3 {
        font-weight: 600 !important;
        color: #38BDF8 !important;
        margin-bottom: 15px !important;
    }
    
    div[data-testid="stColumn"] {
        background-color: #1E293B;
        padding: 24px !important;
        border-radius: 16px !important;
        border: 1px solid #334155;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    
    div[data-testid="stFileUploader"] {
        background-color: #0F172A;
        border: 2px dashed #475569 !important;
        border-radius: 12px !important;
        padding: 10px;
    }
    
    input, textarea {
        background-color: #0F172A !important;
        color: #FFFFFF !important;
        border: 1px solid #475569 !important;
        border-radius: 8px !important;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
        border: 1px solid #38BDF8;
        border-radius: 12px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 10px 15px -3px rgba(56, 189, 248, 0.1);
        margin-bottom: 15px;
    }
    .metric-title {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #94A3B8;
        margin-bottom: 5px;
    }
    .metric-value {
        font-size: 32px;
        font-weight: 700;
        color: #38BDF8;
    }
    
    .block-container {
        padding-top: 2rem !important;
    }
    </style>
""", unsafe_allow_html=True)

CSV_FILE = "registro_calificaciones.csv"

# -----------------------------------------------------------------------------
# 2. CLIENTE GEMINI Y LLAMADA A LA API
# -----------------------------------------------------------------------------
def get_gemini_client():
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        st.error("No se encontró 'GEMINI_API_KEY' en los Secrets de Streamlit ni en las variables de entorno.")
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
                else:
                    st.error("Se ha alcanzado el límite de cuota temporal de la API.")
                    return None
            elif "503" in str(e):
                if intento < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    st.error("El servicio está temporalmente saturado (503). Inténtalo más tarde.")
                    return None
            else:
                st.error(f"Error en la API de Google Gemini: {e}")
                return None
        except Exception as ex:
            st.error(f"Error inesperado al conectar con el modelo: {ex}")
            return None
    return None

# -----------------------------------------------------------------------------
# 3. GESTIÓN DEL REGISTRO LOCAL CSV / EXCEL
# -----------------------------------------------------------------------------
def cargar_registro():
    if os.path.exists(CSV_FILE):
        try:
            return pd.read_csv(CSV_FILE, on_bad_lines='skip')
        except Exception:
            return pd.DataFrame(columns=["Docente", "Estudiante", "Puntaje", "Nota", "Fecha"])
    return pd.DataFrame(columns=["Docente", "Estudiante", "Puntaje", "Nota", "Fecha"])

def guardar_registro(df):
    df.to_csv(CSV_FILE, index=False)

def exportar_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Calificaciones')
    return output.getvalue()

# -----------------------------------------------------------------------------
# 4. GENERACIÓN DE INFORME PDF
# -----------------------------------------------------------------------------
def generar_pdf_informe(nombre_docente, nombre_estudiante, nota, puntaje, feedback_texto):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40,
        title=f"Informe de Evaluación - {nombre_estudiante}",
        author=nombre_docente if nombre_docente else "Docente Evaluador"
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'], fontSize=16, leading=20, textColor=colors.HexColor('#1E293B'), spaceAfter=12
    )
    body_style = ParagraphStyle(
        'DocBody', parent=styles['Normal'], fontSize=9, leading=13, textColor=colors.HexColor('#334155'), spaceAfter=6
    )

    story = [Paragraph("Informe de Evaluación y Retroalimentación", title_style), Spacer(1, 8)]

    data = [
        [Paragraph("<b>Docente:</b>", body_style), Paragraph(nombre_docente if nombre_docente else "No especificado", body_style)],
        [Paragraph("<b>Estudiante:</b>", body_style), Paragraph(nombre_estudiante if nombre_estudiante else "No especificado", body_style)],
        [Paragraph("<b>Puntaje Obt.:</b>", body_style), Paragraph(str(puntaje), body_style)],
        [Paragraph("<b>Nota Final:</b>", body_style), Paragraph(str(nota), body_style)]
    ]
    
    t = Table(data, colWidths=[100, 420])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    
    story.append(t)
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Detalle de Retroalimentación Formativa:</b>", body_style))
    story.append(Spacer(1, 4))
    
    for linea in feedback_texto.split('\n'):
        linea_limpia = linea.strip()
        if linea_limpia:
            linea_escapada = linea_limpia.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            story.append(Paragraph(linea_escapada, body_style))
        else:
            story.append(Spacer(1, 3))
            
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def extraer_metrica(patron, texto, valor_defecto="N/A"):
    match = re.search(patron, texto, re.IGNORECASE)
    return match.group(1).strip() if match else valor_defecto

# -----------------------------------------------------------------------------
# 5. INTERFAZ Y FLUJO PRINCIPAL
# -----------------------------------------------------------------------------
def main():
    st.markdown("""
        <div style='text-align: center; padding-bottom: 25px;'>
            <h1 style='margin-bottom: 0px;'>✨ EduEvalua AI</h1>
            <p style='color: #94A3B8; font-size: 16px; margin-top: 5px;'>Sistemas Avanzados de Retroalimentación Docente con Inteligencia Artificial</p>
        </div>
    """, unsafe_allow_html=True)

    col_izq, col_der = st.columns([1, 1], gap="large")

    with col_izq:
        st.subheader("🛠️ Configuración y Entradas")
        
        profesor = st.text_input("Nombre del Profesor/a", placeholder="Ej. Carlos Mendoza")
        estudiante = st.text_input("Nombre del Estudiante", placeholder="Ej. Francisca Silva")

        st.markdown("<p style='font-weight:600; color:#94A3B8; margin-top:10px; margin-bottom:5px;'>1. Rúbrica de Evaluación</p>", unsafe_allow_html=True)
        opcion_rubrica = st.radio("Formato Rúbrica", ["Texto directo", "Archivo (Imagen/PDF)"], horizontal=True, label_visibility="collapsed")
        
        rubrica_parts = []
        if opcion_rubrica == "Texto directo":
            rubrica_texto = st.text_area("Pegue la rúbrica detallada aquí", height=100, placeholder="Criterios, niveles y ponderaciones...")
            if rubrica_texto.strip():
                rubrica_parts.append(f"--- RÚBRICA DE EVALUACIÓN ---\n{rubrica_texto}")
        else:
            rubrica_file = st.file_uploader("Subir Rúbrica (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"], key="rubrica_file")
            if rubrica_file:
                rubrica_parts.append(types.Part.from_bytes(data=rubrica_file.read(), mime_type=rubrica_file.type))
                rubrica_parts.append("El archivo anterior corresponde a la RÚBRICA DE EVALUACIÓN.")

        st.markdown("<p style='font-weight:600; color:#94A3B8; margin-top:10px; margin-bottom:5px;'>2. Trabajo del Estudiante</p>", unsafe_allow_html=True)
        opcion_trabajo = st.radio("Formato Trabajo", ["Texto directo", "Archivo (Imagen/PDF)"], horizontal=True, label_visibility="collapsed")
        
        trabajo_parts = []
        if opcion_trabajo == "Texto directo":
            trabajo_texto = st.text_area("Pegue el trabajo o respuesta del estudiante", height=120, placeholder="Texto o respuestas a calificar...")
            if trabajo_texto.strip():
                trabajo_parts.append(f"--- TRABAJO DEL ESTUDIANTE ---\n{trabajo_texto}")
        else:
            trabajo_file = st.file_uploader("Subir Trabajo (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"], key="trabajo_file")
            if trabajo_file:
                trabajo_parts.append(types.Part.from_bytes(data=trabajo_file.read(), mime_type=trabajo_file.type))
                trabajo_parts.append("El archivo anterior corresponde al TRABAJO ENTREGADO POR EL ESTUDIANTE.")

        evaluar_btn = st.button("🚀 Evaluar Entrega", type="primary", use_container_width=True)

    with col_der:
        st.subheader("📋 Resultados y Devolución")
        
        if evaluar_btn:
            if not rubrica_parts:
                st.warning("Debes ingresar o adjuntar una rúbrica de evaluación.")
                return
            if not trabajo_parts:
                st.warning("Debes ingresar o adjuntar el trabajo a calificar.")
                return

            client = get_gemini_client()
            
            prompt_sistema = """
Eres un asistente experto en evaluación académica y pedagógica.
Evalúa rigurosamente el trabajo del estudiante contrastándolo únicamente con la rúbrica proporcionada.
Debes responder SIEMPRE con el siguiente formato exacto al inicio de tu respuesta para permitir la extracción de datos:

[PUNTAJE_OBTENIDO]: <valor numérico obtenido / total, ej: 18/20 o 85/100>
[NOTA_FINAL]: <nota final según escala establecida o nota de 1.0 a 7.0 / 1 a 10>

A continuación, redacta un informe estructurado que incluya:
1. Resumen Ejecutivo de la Evaluación.
2. Desglose detallado por cada criterio de la rúbrica (Nivel alcanzado y justificación).
3. Fortalezas observadas.
4. Oportunidades de mejora concretas y accionables.
            """.strip()

            contents = rubrica_parts + trabajo_parts

            with st.spinner("Analizando con Gemini..."):
                resultado = generar_evaluacion_con_reintentos(client, contents, prompt_sistema)

            if resultado:
                puntaje = extraer_metrica(r'\[PUNTAJE_OBTENIDO\]:\s*(.*)', resultado)
                nota = extraer_metrica(r'\[NOTA_FINAL\]:\s*(.*)', resultado)
                
                feedback_limpio = re.sub(r'\[(PUNTAJE_OBTENIDO|NOTA_FINAL)\]:.*', '', resultado).strip()

                st.session_state["ultima_evaluacion"] = {
                    "docente": profesor,
                    "estudiante": estudiante,
                    "puntaje": puntaje,
                    "nota": nota,
                    "feedback": feedback_limpio,
                    "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
                }

                df_actual = cargar_registro()
                nueva_fila = pd.DataFrame([{
                    "Docente": profesor if profesor else "No especificado",
                    "Estudiante": estudiante if estudiante else "No especificado",
                    "Puntaje": puntaje,
                    "Nota": nota,
                    "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
                }])
                df_actual = pd.concat([df_actual, nueva_fila], ignore_index=True)
                guardar_registro(df_actual)

        if "ultima_evaluacion" in st.session_state:
            eval_data = st.session_state["ultima_evaluacion"]

            m_col1, m_col2 = st.columns(2)
            with m_col1:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">Puntaje Obtenido</div>
                        <div class="metric-value">{eval_data['puntaje']}</div>
                    </div>
                """, unsafe_allow_html=True)
            with m_col2:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">Nota Final</div>
                        <div class="metric-value">{eval_data['nota']}</div>
                    </div>
                """, unsafe_allow_html=True)

            st.markdown(eval_data['feedback'])

            pdf_bytes = generar_pdf_informe(
                eval_data["docente"],
                eval_data["estudiante"],
                eval_data["nota"],
                eval_data["puntaje"],
                eval_data["feedback"]
            )

            st.download_button(
                label="📥 Descargar Informe en PDF",
                data=pdf_bytes,
                file_name=f"Informe_{eval_data['estudiante'].replace(' ', '_') or 'Estudiante'}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        else:
            st.info("Ingresa los datos y presiona 'Evaluar Entrega' para generar el informe.")

    # Sección Historial / Exportación
    st.markdown("---")
    st.subheader("📊 Historial de Evaluaciones")
    df_registro = cargar_registro()
    
    if not df_registro.empty:
        st.dataframe(df_registro, use_container_width=True)
        col_exp1, col_exp2 = st.columns([1, 4])
        with col_exp1:
            try:
                excel_data = exportar_excel(df_registro)
                st.download_button(
                    label="Exportar a Excel",
                    data=excel_data,
                    file_name="calificaciones.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception:
                csv_bytes = df_registro.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Exportar a CSV",
                    data=csv_bytes,
                    file_name="calificaciones.csv",
                    mime="text/csv"
                )
    else:
        st.caption("Aún no hay evaluaciones registradas en esta sesión.")

if __name__ == "__main__":
    main()