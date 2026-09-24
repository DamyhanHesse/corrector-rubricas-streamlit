import os
import time
import io
import base64
import pandas as pd
import streamlit as st
from openai import OpenAI

# Librerías para procesamiento de PDF e Imágenes
from pypdf import PdfReader

# Librerías para generación de PDF en ReportLab
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# -----------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Corrector y Retroalimentador de Pruebas",
    layout="wide",
    initial_sidebar_state="expanded"
)

CSV_FILE = "registro_calificaciones.csv"
MODEL_NVIDIA = "deepseek-ai/deepseek-v4.1-flash"

# -----------------------------------------------------------------------------
# 2. CLIENTE NVIDIA NIM Y AUXILIARES DE ARCHIVO
# -----------------------------------------------------------------------------
def get_nvidia_client():
    api_key = st.secrets.get("NVIDIA_API_KEY")
    if not api_key:
        st.error("No se encontró 'NVIDIA_API_KEY' en los Secrets de Streamlit.")
        st.stop()
    return OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )

def extraer_texto_o_base64(file_bytes, filename, mime_type):
    """
    Si es PDF, extrae el texto. Si es imagen, genera una cadena Base64.
    """
    if "pdf" in mime_type.lower() or filename.lower().endswith(".pdf"):
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            texto = ""
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    texto += t + "\n"
            return "text", texto if texto.strip() else "No se pudo extraer texto seleccionable del PDF."
        except Exception as e:
            return "text", f"Error al leer PDF: {e}"
    else:
        # Es una imagen (PNG / JPG)
        b64_img = base64.b64encode(file_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64_img}"
        return "image_url", data_url

def generar_evaluacion_nvidia(client, prompt_sistema, rubrica_data, prueba_data):
    messages_payload = [{"role": "system", "content": prompt_sistema}]
    
    content_user = []
    
    # 1. Agregar Rúbrica
    tipo_r, val_r = rubrica_data
    if tipo_r == "text":
        content_user.append({"type": "text", "text": f"--- RÚBRICA DE EVALUACIÓN ---\n{val_r}"})
    elif tipo_r == "image_url":
        content_user.append({"type": "text", "text": "--- RÚBRICA EN IMAGEN ---"})
        content_user.append({"type": "image_url", "image_url": {"url": val_r}})
        
    # 2. Agregar Prueba del Estudiante
    tipo_p, val_p = prueba_data
    if tipo_p == "text":
        content_user.append({"type": "text", "text": f"--- PRUEBA DEL ESTUDIANTE ---\n{val_p}"})
    elif tipo_p == "image_url":
        content_user.append({"type": "text", "text": "--- PRUEBA EN IMAGEN ---"})
        content_user.append({"type": "image_url", "image_url": {"url": val_p}})

    messages_payload.append({"role": "user", "content": content_user})

    for intento in range(3):
        try:
            response = client.chat.completions.create(
                model=MODEL_NVIDIA,
                messages=messages_payload,
                temperature=0.2,
                max_tokens=2048
            )
            return response.choices[0].message.content
        except Exception as e:
            if "429" in str(e) or "503" in str(e):
                if intento < 2:
                    time.sleep((intento + 1) * 3)
                    continue
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
    st.caption("Motor de Evaluación con NVIDIA NIM API (DeepSeek V4.1 Flash)")

    col_izq, col_der = st.columns([1, 1], gap="large")

    with col_izq:
        st.subheader("1. Configuración y Entradas")
        
        profesor = st.text_input("Nombre del Profesor/a", placeholder="Ingrese su nombre aquí...")
        estudiante = st.text_input("Nombre del Estudiante", placeholder="Ingrese nombre del estudiante...")

        st.markdown("---")
        st.markdown("**Rúbrica de Evaluación**")
        opcion_rubrica = st.radio("Formato de Rúbrica", ["Texto directo", "Archivo (Imagen/PDF)"], horizontal=True)
        
        rubrica_data = None
        if opcion_rubrica == "Texto directo":
            rubrica_txt = st.text_area("Pegue la rúbrica aquí", height=150)
            if rubrica_txt.strip():
                rubrica_data = ("text", rubrica_txt)
        else:
            rubrica_file = st.file_uploader("Subir Rúbrica (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"], key="rubrica_file")
            if rubrica_file:
                bytes_r = rubrica_file.read()
                rubrica_data = extraer_texto_o_base64(bytes_r, rubrica_file.name, rubrica_file.type)

        st.markdown("---")
        st.markdown("**Prueba del Estudiante**")
        prueba_file = st.file_uploader("Subir Prueba (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"], key="prueba_file")
        
        prueba_data = None
        if prueba_file:
            bytes_p = prueba_file.read()
            prueba_data = extraer_texto_o_base64(bytes_p, prueba_file.name, prueba_file.type)

        btn_evaluar = st.button("🚀 Evaluar Prueba", use_container_width=True, type="primary")

    with col_der:
        st.subheader("2. Resultado de la Evaluación")
        
        if btn_evaluar:
            if not rubrica_data:
                st.warning("Debe ingresar o adjuntar una rúbrica.")
                return
            if not prueba_data:
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

            with st.spinner("Analizando la prueba con NVIDIA NIM..."):
                resultado = generar_evaluacion_nvidia(client, prompt_sistema, rubrica_data, prueba_data)
                
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

            # Descargar PDF
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