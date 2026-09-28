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
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS VISUALES CORPORATIVOS (B2B SaaS)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="EduEvalua AI",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Inter', -apple-system, sans-serif;
        background-color: #F3F4F6; /* Fondo gris claro corporativo */
        color: #111827; /* Texto principal oscuro */
    }
    
    h1, h2, h3, h4 {
        font-weight: 600 !important;
        color: #111827 !important;
        letter-spacing: -0.02em;
    }
    
    /* Contenedores principales (Tarjetas) */
    div[data-testid="stColumn"] {
        background-color: #FFFFFF;
        padding: 2rem !important;
        border-radius: 8px !important;
        border: 1px solid #E5E7EB;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
    }
    
    /* Zona de carga de archivos */
    div[data-testid="stFileUploader"] {
        background-color: #F9FAFB;
        border: 1px dashed #D1D5DB !important;
        border-radius: 6px !important;
        padding: 10px;
    }
    
    /* Inputs y Textareas */
    input, textarea {
        background-color: #FFFFFF !important;
        color: #111827 !important;
        border: 1px solid #D1D5DB !important;
        border-radius: 6px !important;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    }
    input:focus, textarea:focus {
        border-color: #2563EB !important;
        box-shadow: 0 0 0 1px #2563EB !important;
    }
    
    /* Botón Primario */
    button[kind="primary"] {
        background-color: #2563EB !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
    }
    button[kind="primary"]:hover {
        background-color: #1D4ED8 !important;
    }
    
    /* Tarjetas de Métricas de Evaluación */
    .metric-card {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-left: 4px solid #2563EB;
        border-radius: 6px;
        padding: 16px;
        text-align: left;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        margin-bottom: 1rem;
    }
    .metric-title {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #6B7280;
        margin-bottom: 0.25rem;
        font-weight: 600;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #111827;
    }
    
    /* Ajuste de márgenes superiores */
    .block-container {
        padding-top: 2rem !important;
        max-width: 1400px;
    }
    
    /* Estilo de subtextos y etiquetas */
    .section-label {
        font-weight: 600;
        color: #374151;
        font-size: 0.875rem;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
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
        st.error("No se encontró 'GEMINI_API_KEY' en la configuración del entorno.")
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
                    st.error("Límite de cuota temporal de la API alcanzado.")
                    return None
            elif "503" in str(e):
                if intento < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    st.error("Servicio temporalmente saturado (503).")
                    return None
            else:
                st.error(f"Error en la API: {e}")
                return None
        except Exception as ex:
            st.error(f"Error de conexión: {ex}")
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
        author=nombre_docente if nombre_docente else "Evaluador Institucional"
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'], fontSize=16, leading=20, textColor=colors.HexColor('#111827'), spaceAfter=15
    )
    body_style = ParagraphStyle(
        'DocBody', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor('#374151'), spaceAfter=8
    )

    story = [Paragraph("Informe de Evaluación Institucional", title_style), Spacer(1, 10)]

    data = [
        [Paragraph("<b>Evaluador:</b>", body_style), Paragraph(nombre_docente if nombre_docente else "No especificado", body_style)],
        [Paragraph("<b>Estudiante:</b>", body_style), Paragraph(nombre_estudiante if nombre_estudiante else "No especificado", body_style)],
        [Paragraph("<b>Puntaje:</b>", body_style), Paragraph(str(puntaje), body_style)],
        [Paragraph("<b>Nota Final:</b>", body_style), Paragraph(str(nota), body_style)]
    ]
    
    t = Table(data, colWidths=[100, 420])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F9FAFB')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#D1D5DB')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    
    story.append(t)
    story.append(Spacer(1, 15))
    story.append(Paragraph("<b>Detalle de Retroalimentación:</b>", body_style))
    story.append(Spacer(1, 5))
    
    for linea in feedback_texto.split('\n'):
        linea_limpia = linea.strip()
        if linea_limpia:
            linea_escapada = linea_limpia.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            story.append(Paragraph(linea_escapada, body_style))
        else:
            story.append(Spacer(1, 4))
            
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
        <div style='padding-bottom: 20px; border-bottom: 1px solid #E5E7EB; margin-bottom: 25px;'>
            <h1 style='margin-bottom: 0px;'>EduEvalua AI</h1>
            <p style='color: #6B7280; font-size: 15px; margin-top: 4px;'>Sistema de Análisis y Retroalimentación Pedagógica</p>
        </div>
    """, unsafe_allow_html=True)

    col_izq, col_der = st.columns([1, 1], gap="large")

    with col_izq:
        st.subheader("Parámetros de Evaluación")
        
        profesor = st.text_input("Nombre del Evaluador", value="")
        estudiante = st.text_input("Nombre del Estudiante", value="")

        st.markdown("<div class='section-label'>1. Instrumento de Evaluación (Rúbrica)</div>", unsafe_allow_html=True)
        opcion_rubrica = st.radio("Formato de rúbrica", ["Texto directo", "Archivo adjunto (PDF/Imagen)"], horizontal=True, label_visibility="collapsed")
        
        rubrica_parts = []
        if opcion_rubrica == "Texto directo":
            rubrica_texto = st.text_area("Criterios de evaluación", height=100, label_visibility="collapsed")
            if rubrica_texto.strip():
                rubrica_parts.append(f"--- RÚBRICA DE EVALUACIÓN ---\n{rubrica_texto}")
        else:
            rubrica_file = st.file_uploader("Cargar documento de rúbrica", type=["pdf", "png", "jpg", "jpeg"], key="rubrica_file")
            if rubrica_file:
                rubrica_parts.append(types.Part.from_bytes(data=rubrica_file.read(), mime_type=rubrica_file.type))
                rubrica_parts.append("El archivo anterior corresponde a la RÚBRICA DE EVALUACIÓN.")

        st.markdown("<div class='section-label'>2. Evidencia del Estudiante</div>", unsafe_allow_html=True)
        opcion_trabajo = st.radio("Formato de evidencia", ["Texto directo", "Archivo adjunto (PDF/Imagen)"], horizontal=True, label_visibility="collapsed")
        
        trabajo_parts = []
        if opcion_trabajo == "Texto directo":
            trabajo_texto = st.text_area("Contenido a evaluar", height=120, label_visibility="collapsed")
            if trabajo_texto.strip():
                trabajo_parts.append(f"--- TRABAJO DEL ESTUDIANTE ---\n{trabajo_texto}")
        else:
            trabajo_file = st.file_uploader("Cargar trabajo del estudiante", type=["pdf", "png", "jpg", "jpeg"], key="trabajo_file")
            if trabajo_file:
                trabajo_parts.append(types.Part.from_bytes(data=trabajo_file.read(), mime_type=trabajo_file.type))
                trabajo_parts.append("El archivo anterior corresponde al TRABAJO ENTREGADO POR EL ESTUDIANTE.")

        st.markdown("<br>", unsafe_allow_html=True)
        evaluar_btn = st.button("Ejecutar Análisis", type="primary", use_container_width=True)

    with col_der:
        st.subheader("Resultados del Análisis")
        
        if evaluar_btn:
            if not rubrica_parts:
                st.warning("Se requiere un instrumento de evaluación (rúbrica).")
                return
            if not trabajo_parts:
                st.warning("Se requiere la evidencia del estudiante.")
                return

            client = get_gemini_client()
            
            prompt_sistema = """
Eres un sistema experto en evaluación académica.
Evalúa rigurosamente el trabajo del estudiante contrastándolo únicamente con la rúbrica proporcionada.
Debes responder SIEMPRE con el siguiente formato exacto al inicio de tu respuesta para permitir la extracción de datos:

[PUNTAJE_OBTENIDO]: <valor numérico obtenido / total>
[NOTA_FINAL]: <nota final según escala>

A continuación, redacta un informe estructurado y profesional que incluya:
1. Resumen Ejecutivo de la Evaluación.
2. Desglose por criterio de la rúbrica (Nivel alcanzado y justificación).
3. Fortalezas identificadas.
4. Oportunidades de mejora accionables.
Evita el lenguaje redundante o emocional. Sé objetivo y directo.
            """.strip()

            contents = rubrica_parts + trabajo_parts

            with st.spinner("Procesando datos con modelo de IA..."):
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
                        <div class="metric-title">Calificación Final</div>
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
                label="Descargar Informe Oficial (PDF)",
                data=pdf_bytes,
                file_name=f"Informe_{eval_data['estudiante'].replace(' ', '_') or 'Estudiante'}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        else:
            st.info("El sistema está listo. Complete los parámetros y ejecute el análisis para visualizar los resultados.")

    st.markdown("<br><hr style='border: 1px solid #E5E7EB;'><br>", unsafe_allow_html=True)
    st.subheader("Registro Histórico de Operaciones")
    df_registro = cargar_registro()
    
    if not df_registro.empty:
        st.dataframe(df_registro, use_container_width=True)
        col_exp1, col_exp2 = st.columns([1, 4])
        with col_exp1:
            try:
                excel_data = exportar_excel(df_registro)
                st.download_button(
                    label="Exportar Dataset (Excel)",
                    data=excel_data,
                    file_name="calificaciones_historico.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception:
                csv_bytes = df_registro.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Exportar Dataset (CSV)",
                    data=csv_bytes,
                    file_name="calificaciones_historico.csv",
                    mime="text/csv"
                )
    else:
        st.caption("No existen registros de evaluación en la base de datos local.")

if __name__ == "__main__":
    main()