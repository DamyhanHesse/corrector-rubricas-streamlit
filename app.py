import os
import time
import io
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
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS NATIVOS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Corrector y Retroalimentador de Pruebas",
    layout="wide",
    initial_sidebar_state="expanded"
)

CSV_FILE = "registro_calificaciones.csv"

# -----------------------------------------------------------------------------
# 2. CLIENTE GEMINI Y BUCLE DE REINTENTOS ESCALONADOS
# -----------------------------------------------------------------------------
def get_gemini_client():
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        st.error("No se encontró 'GEMINI_API_KEY' en los Secrets de Streamlit.")
        st.stop()
    return genai.Client(api_key=api_key)

def generar_evaluacion_con_reintentos(client, contents, prompt_sistema, max_retries=3):
    """
    Realiza llamadas al modelo gemini-3.6-flash con reintentos
    escalonados para manejar saturación puntual o cuotas de peticiones.
    """
    model_id = "gemini-3.6-flash"
    
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
                    wait_time = (intento + 1) * 4
                    time.sleep(wait_time)
                    continue
                else:
                    st.error("⚠️ Se ha alcanzado el límite de cuota de la API de Gemini.")
                    st.info("Sugerencia: Espera unos instantes o revisa tu cuota en Google AI Studio.")
                    return None
            elif "503" in str(e):
                if intento < max_retries - 1:
                    time.sleep(3)
                    continue
                else:
                    st.error("⚠️ El servicio de Gemini está temporalmente saturado (503). Inténtalo más tarde.")
                    return None
            else:
                st.error(f"Error en la API de Gemini: {e}")
                return None
        except Exception as ex:
            st.error(f"Error inesperado durante la ejecución: {ex}")
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
    else:
        return pd.DataFrame(columns=["Docente", "Estudiante", "Puntaje", "Nota", "Fecha"])

def guardar_registro(df):
    df.to_csv(CSV_FILE, index=False)

def exportar_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Calificaciones')
    return output.getvalue()

# -----------------------------------------------------------------------------
# 4. GENERACIÓN DE INFORME PDF CON REPORTLAB
# -----------------------------------------------------------------------------
def generar_pdf_informe(nombre_docente, nombre_estudiante, nota, puntaje, feedback_texto):
    buffer = io.BytesIO()
    
    # Declaración explícita de metadatos para evitar la etiqueta (anonymous)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
        title=f"Informe de Evaluación - {nombre_estudiante}",
        author=nombre_docente if nombre_docente else "Docente Evaluador"
    )
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1E293B'),
        spaceAfter=12
    )
    
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#334155'),
        spaceAfter=8
    )

    story = []

    story.append(Paragraph("Informe de Evaluación y Retroalimentación", title_style))
    story.append(Spacer(1, 10))

    data = [
        [Paragraph("<b>Docente:</b>", body_style), Paragraph(nombre_docente if nombre_docente else "No especificado", body_style)],
        [Paragraph("<b>Estudiante:</b>", body_style), Paragraph(nombre_estudiante if nombre_estudiante else "No especificado", body_style)],
        [Paragraph("<b>Puntaje Obt.:</b>", body_style), Paragraph(str(puntaje), body_style)],
        [Paragraph("<b>Nota Final:</b>", body_style), Paragraph(str(nota), body_style)]
    ]
    
    t = Table(data, colWidths=[100, 400])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    
    story.append(t)
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("<b>Detalle de Retroalimentación Formativa:</b>", body_style))
    story.append(Spacer(1, 5))
    
    lineas = feedback_texto.split('\n')
    for linea in lineas:
        if linea.strip():
            story.append(Paragraph(linea.replace('<', '&lt;').replace('>', '&gt;'), body_style))
        else:
            story.append(Spacer(1, 4))
            
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# -----------------------------------------------------------------------------
# 5. INTERFAZ DE USUARIO STREAMLIT (LAYOUT DOS COLUMNAS)
# -----------------------------------------------------------------------------
def main():
    st.title("📝 Corrector y Retroalimentador de Pruebas")
    st.caption("Motor de Evaluación con Google Gemini API")

    col_izq, col_der = st.columns([1, 1], gap="large")

    with col_izq:
        st.subheader("1. Configuración y Entradas")
        
        profesor = st.text_input("Nombre del Profesor/a", placeholder="Ingrese su nombre aquí...")
        estudiante = st.text_input("Nombre del Estudiante", placeholder="Ingrese nombre del estudiante...")

        st.markdown("---")
        st.markdown("**Rúbrica de Evaluación**")
        opcion_rubrica = st.radio("Formato de Rúbrica", ["Texto directo", "Archivo (Imagen/PDF)"], horizontal=True)
        
        rubrica_content = None
        if opcion_rubrica == "Texto directo":
            rubrica_content = st.text_area("Pegue la rúbrica aquí", height=150)
        else:
            rubrica_file = st.file_uploader("Subir Rúbrica (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"], key="rubrica_file")
            if rubrica_file:
                rubrica_bytes = rubrica_file.read()
                rubrica_content = types.Part.from_bytes(data=rubrica_bytes, mime_type=rubrica_file.type)

        st.markdown("---")
        st.markdown("**Prueba del Estudiante**")
        prueba_file = st.file_uploader("Subir Prueba (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"], key="prueba_file")
        
        prueba_part = None
        if prueba_file:
            prueba_bytes = prueba_file.read()
            prueba_part = types.Part.from_bytes(data=prueba_bytes, mime_type=prueba_file.type)

        btn_evaluar = st.button("🚀 Evaluar Prueba", use_container_width=True, type="primary")

    with col_der:
        st.subheader("2. Resultado de la Evaluación")
        
        if btn_evaluar:
            if not rubrica_content:
                st.warning("Debe ingresar o adjuntar una rúbrica.")
                return
            if not prueba_part:
                st.warning("Debe adjuntar la prueba del estudiante.")
                return

            client = get_gemini_client()
            
            prompt_sistema = """
            Eres un asistente docente experto en evaluación educativa.
            Analiza la rúbrica entregada y la prueba del estudiante.
            
            Debes entregar la respuesta con la siguiente estructura exacta al inicio:
            NOTA: [Nota obtenida, ej: 6.5]
            PUNTAJE: [Puntaje obtenido / Puntaje total, ej: 28/30]
            
            Posteriormente, detalla el feedback formativo estructurado:
            - Fortalezas observadas.
            - Aspectos a mejorar según la rúbrica.
            - Sugerencias concretas para el estudiante.
            """

            contents = []
            if isinstance(rubrica_content, str):
                contents.append(f"RÚBRICA DE EVALUACIÓN:\n{rubrica_content}")
            else:
                contents.append(rubrica_content)
                
            contents.append(prueba_part)
            
            with st.spinner("Analizando la prueba y generando retroalimentación..."):
                resultado = generar_evaluacion_con_reintentos(client, contents, prompt_sistema)
                
            if resultado:
                st.session_state["ultimo_resultado"] = resultado
                st.session_state["ultimo_estudiante"] = estudiante if estudiante else "Estudiante"
                st.session_state["ultimo_profesor"] = profesor if profesor else "Docente"

                nota_val = "N/A"
                puntaje_val = "N/A"
                for line in resultado.split('\n'):
                    if line.startswith("NOTA:"):
                        nota_val = line.replace("NOTA:", "").strip()
                    elif line.startswith("PUNTAJE:"):
                        puntaje_val = line.replace("PUNTAJE:", "").strip()

                st.session_state["ultima_nota"] = nota_val
                st.session_state["ultimo_puntaje"] = puntaje_val

                # Registrar en CSV local
                df_actual = cargar_registro()
                nuevo_registro = pd.DataFrame([{
                    "Docente": profesor if profesor else "Docente",
                    "Estudiante": estudiante if estudiante else "Estudiante",
                    "Puntaje": puntaje_val,
                    "Nota": nota_val,
                    "Fecha": time.strftime("%Y-%m-%d %H:%M:%S")
                }])
                df_actual = pd.concat([df_actual, nuevo_registro], ignore_index=True)
                guardar_registro(df_actual)

        if "ultimo_resultado" in st.session_state:
            st.success("Evaluación completada con éxito.")
            
            m1, m2 = st.columns(2)
            m1.metric("Nota Obtenida", st.session_state.get("ultima_nota", "N/A"))
            m2.metric("Puntaje Obt.", st.session_state.get("ultimo_puntaje", "N/A"))

            st.markdown("### Retroalimentación Formativa")
            st.write(st.session_state["ultimo_resultado"])

            # Generación y descarga de PDF
            pdf_bytes = generar_pdf_informe(
                st.session_state.get("ultimo_profesor", "Docente"),
                st.session_state.get("ultimo_estudiante", "Estudiante"),
                st.session_state.get("ultima_nota", "N/A"),
                st.session_state.get("ultimo_puntaje", "N/A"),
                st.session_state["ultimo_resultado"]
            )
            
            st.download_button(
                label="📄 Descargar Informe PDF",
                data=pdf_bytes,
                file_name=f"Informe_{st.session_state.get('ultimo_estudiante', 'Estudiante')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

    # -------------------------------------------------------------------------
    # SECCIÓN INFERIOR: PLANILLA DE REGISTRO ACUMULADO
    # -------------------------------------------------------------------------
    st.markdown("---")
    st.subheader("📊 Registro Acumulado de Calificaciones")
    
    df_registro = cargar_registro()
    if not df_registro.empty:
        st.dataframe(df_registro, use_container_width=True)
        excel_data = exportar_excel(df_registro)
        st.download_button(
            label="📥 Exportar Registro a Excel (.xlsx)",
            data=excel_data,
            file_name="registro_calificaciones.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Aún no hay calificaciones registradas.")

if __name__ == "__main__":
    main()