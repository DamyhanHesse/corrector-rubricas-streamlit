import os
import time
import io
import base64
import pandas as pd
import streamlit as st
from openai import OpenAI
from pypdf import PdfReader

# Librerías para generación de PDF en ReportLab
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# -----------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA Y CONSTANTES
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Corrector y Retroalimentador de Pruebas",
    layout="wide",
    initial_sidebar_state="expanded"
)

CSV_FILE = "registro_calificaciones.csv"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL_ID = "meta/llama-3.3-70b-instruct"

# -----------------------------------------------------------------------------
# 2. CLIENTE NVIDIA NIM Y EVALUACIÓN CON REINTENTOS ESCALONADOS
# -----------------------------------------------------------------------------
def get_nvidia_client():
    api_key = st.secrets.get("NVIDIA_API_KEY")
    if not api_key:
        st.error("No se encontró 'NVIDIA_API_KEY' en los Secrets de Streamlit.")
        st.stop()
    return OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)

def procesar_archivo_a_texto_o_b64(file_uploader_obj):
    """Convierte el archivo a texto plano (PDF) o cadena base64 (Imágenes)."""
    if file_uploader_obj is None:
        return None
    
    file_bytes = file_uploader_obj.read()
    mime_type = file_uploader_obj.type

    if mime_type == "application/pdf":
        try:
            pdf_reader = PdfReader(io.BytesIO(file_bytes))
            texto_extraido = "\n".join([page.extract_text() or "" for page in pdf_reader.pages])
            return {"tipo": "texto", "contenido": texto_extraido}
        except Exception as e:
            st.error(f"Error al leer el archivo PDF: {e}")
            return None
    elif mime_type in ["image/png", "image/jpeg", "image/jpg"]:
        b64_encoded = base64.b64encode(file_bytes).decode("utf-8")
        return {"tipo": "imagen", "contenido": f"data:{mime_type};base64,{b64_encoded}"}
    return None

def generar_evaluacion_nvidia(client, prompt_sistema, contenido_rubrica, contenido_prueba, max_retries=3):
    """
    Envía la solicitud a NVIDIA NIM manejando reintentos exponenciales ante saturación.
    """
    content_payload = []

    # Procesar Rúbrica
    if isinstance(contenido_rubrica, str):
        content_payload.append({"type": "text", "text": f"RÚBRICA DE EVALUACIÓN:\n{contenido_rubrica}"})
    elif isinstance(contenido_rubrica, dict):
        if contenido_rubrica["tipo"] == "texto":
            content_payload.append({"type": "text", "text": f"RÚBRICA DE EVALUACIÓN:\n{contenido_rubrica['contenido']}"})
        elif contenido_rubrica["tipo"] == "imagen":
            content_payload.append({"type": "text", "text": "RÚBRICA DE EVALUACIÓN (IMAGEN):"})
            content_payload.append({"type": "image_url", "image_url": {"url": contenido_rubrica["contenido"]}})

    # Procesar Prueba
    if isinstance(contenido_prueba, dict):
        if contenido_prueba["tipo"] == "texto":
            content_payload.append({"type": "text", "text": f"PRUEBA DEL ESTUDIANTE:\n{contenido_prueba['contenido']}"})
        elif contenido_prueba["tipo"] == "imagen":
            content_payload.append({"type": "text", "text": "PRUEBA DEL ESTUDIANTE (IMAGEN):"})
            content_payload.append({"type": "image_url", "image_url": {"url": contenido_prueba["contenido"]}})

    messages = [
        {"role": "system", "content": prompt_sistema},
        {"role": "user", "content": content_payload}
    ]

    for intento in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=messages,
                temperature=0.2,
                max_tokens=2048
            )
            return response.choices[0].message.content
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "rate limit" in err_msg.lower():
                if intento < max_retries - 1:
                    time.sleep((intento + 1) * 3)
                    continue
                else:
                    st.error("⚠️ Se ha alcanzado el límite de tasa (429) de NVIDIA NIM.")
                    return None
            elif "503" in err_msg or "unavailable" in err_msg.lower():
                if intento < max_retries - 1:
                    time.sleep(4)
                    continue
                else:
                    st.error("⚠️ El servicio de NVIDIA está temporalmente saturado (503). Intente nuevamente.")
                    return None
            else:
                st.error(f"Error en la API de NVIDIA: {e}")
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
# 4. GENERACIÓN DE INFORME PDF CON REPORTLAB
# -----------------------------------------------------------------------------
def generar_pdf_informe(nombre_docente, nombre_estudiante, nota, puntaje, feedback_texto):
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
        title=f"Informe de Evaluación - {nombre_estudiante}",
        author=nombre_docente
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
        [Paragraph("<b>Docente:</b>", body_style), Paragraph(nombre_docente, body_style)],
        [Paragraph("<b>Estudiante:</b>", body_style), Paragraph(nombre_estudiante, body_style)],
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
# 5. INTERFAZ DE USUARIO STREAMLIT
# -----------------------------------------------------------------------------
def main():
    st.title("📝 Corrector y Retroalimentador de Pruebas")
    st.caption("Motor de Evaluación con NVIDIA NIM API")

    col_izq, col_der = st.columns([1, 1], gap="large")

    with col_izq:
        st.subheader("1. Configuración y Entradas")
        
        profesor = st.text_input("Nombre del Profesor/a", value="Prof. Carlos Mendoza")
        estudiante = st.text_input("Nombre del Estudiante", value="Estudiante 1")

        st.markdown("---")
        st.markdown("**Rúbrica de Evaluación**")
        opcion_rubrica = st.radio("Formato de Rúbrica", ["Texto directo", "Archivo (Imagen/PDF)"], horizontal=True)
        
        rubrica_content = None
        if opcion_rubrica == "Texto directo":
            rubrica_content = st.text_area("Pegue la rúbrica aquí", height=150)
        else:
            rubrica_file = st.file_uploader("Subir Rúbrica (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"], key="rubrica_file")
            if rubrica_file:
                rubrica_content = procesar_archivo_a_texto_o_b64(rubrica_file)

        st.markdown("---")
        st.markdown("**Prueba del Estudiante**")
        prueba_file = st.file_uploader("Subir Prueba (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"], key="prueba_file")
        prueba_content = procesar_archivo_a_texto_o_b64(prueba_file) if prueba_file else None

        btn_evaluar = st.button("🚀 Evaluar Prueba", use_container_width=True, type="primary")

    with col_der:
        st.subheader("2. Resultado de la Evaluación")
        
        if btn_evaluar:
            if not rubrica_content:
                st.warning("Debe ingresar o adjuntar una rúbrica.")
                return
            if not prueba_content:
                st.warning("Debe adjuntar la prueba del estudiante.")
                return

            client = get_nvidia_client()
            
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
            
            with st.spinner("Analizando evaluación con NVIDIA NIM..."):
                resultado = generar_evaluacion_nvidia(client, prompt_sistema, rubrica_content, prueba_content)
                
            if resultado:
                st.session_state["ultimo_resultado"] = resultado
                st.session_state["ultimo_estudiante"] = estudiante
                st.session_state["ultimo_profesor"] = profesor

                nota_val = "N/A"
                puntaje_val = "N/A"
                for line in resultado.split('\n'):
                    if line.startswith("NOTA:"):
                        nota_val = line.replace("NOTA:", "").strip()
                    elif line.startswith("PUNTAJE:"):
                        puntaje_val = line.replace("PUNTAJE:", "").strip()

                st.session_state["ultima_nota"] = nota_val
                st.session_state["ultimo_puntaje"] = puntaje_val

                df_actual = cargar_registro()
                nuevo_registro = pd.DataFrame([{
                    "Docente": profesor,
                    "Estudiante": estudiante,
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

            pdf_bytes = generar_pdf_informe(
                st.session_state.get("ultimo_profesor", profesor),
                st.session_state.get("ultimo_estudiante", estudiante),
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