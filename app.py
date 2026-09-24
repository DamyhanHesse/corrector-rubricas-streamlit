import io
import os
import time
import random
import pandas as pd
import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import APIError
from groq import Groq
import pypdf

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ------------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA Y SECRETS
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="Corrector y Retroalimentador de Pruebas",
    layout="wide"
)

# Recuperación segura de API Keys desde Streamlit Secrets
gemini_key = st.secrets.get("GEMINI_API_KEY")
groq_key = st.secrets.get("GROQ_API_KEY")

if not gemini_key:
    st.error("Error: No se ha configurado 'GEMINI_API_KEY' en los Secrets de Streamlit.")
    st.stop()

# Clientes de IA
client_gemini = genai.Client(api_key=gemini_key)
client_groq = Groq(api_key=groq_key) if groq_key else None

MODELO_GEMINI = "gemini-3.6-flash"
MODELO_GROQ = "llama-3.3-70b-versatile"
ARCHIVO_CSV = "registro_calificaciones.csv"

# ------------------------------------------------------------------------------
# 2. FUNCIONES AUXILIARES DE EXTRACCIÓN DE TEXTO
# ------------------------------------------------------------------------------
def extraer_texto_pdf(archivo_bytes):
    """Extrae texto legible de un archivo PDF subido."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(archivo_bytes))
        texto = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                texto += t + "\n"
        return texto.strip()
    except Exception:
        return ""

# ------------------------------------------------------------------------------
# 3. MOTOR DUAL DE EVALUACIÓN (GEMINI CON FAILOVER A GROQ)
# ------------------------------------------------------------------------------
def evaluar_con_ia_multiservidor(contenidos_gemini, texto_prompts_groq, system_instruction):
    """
    Intenta la evaluación con Gemini. Si responde 503/429 (saturación), 
    conmuta automáticamente a Groq (Llama-3.3-70b).
    """
    # INTENTO 1: GOOGLE GEMINI
    try:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2
        )
        response = client_gemini.models.generate_content(
            model=MODELO_GEMINI,
            contents=contenidos_gemini,
            config=config
        )
        return response.text, "Google Gemini 3.6 Flash"
        
    except APIError as e:
        es_saturacion = (e.code == 503 or e.code == 429 or "UNAVAILABLE" in str(e) or "high demand" in str(e))
        if not es_saturacion:
            raise e
        st.toast("⚠️ Servidor Gemini saturado (Error 503). Conmutando a Servidor Secundario (Groq LPU)...", icon="🔄")
    except Exception as e:
        st.toast("⚠️ Error en Gemini. Conmutando a Servidor Secundario (Groq LPU)...", icon="🔄")

    # INTENTO 2: GROQ (RESPALDO DE ALTA DISPONIBILIDAD)
    if client_groq:
        try:
            prompt_completo = f"{system_instruction}\n\n--- DOCUMENTOS Y DATOS DE LA PRUEBA ---\n{texto_prompts_groq}"
            completion = client_groq.chat.completions.create(
                model=MODELO_GROQ,
                messages=[{"role": "user", "content": prompt_completo}],
                temperature=0.2,
                max_tokens=2048
            )
            return completion.choices[0].message.content, "Groq / Llama-3.3-70b (Servidor Secundario)"
        except Exception as groq_err:
            raise RuntimeError(f"Ambos servidores fallaron. Error en servidor secundario: {groq_err}")
    else:
        raise RuntimeError("El servidor de Google está saturado (503) y no se configuró 'GROQ_API_KEY' de respaldo.")

# ------------------------------------------------------------------------------
# 4. GENERACIÓN DE REPORTES EN PDF (REPORTLAB)
# ------------------------------------------------------------------------------
def generar_reporte_pdf(profesor, nota, puntaje, feedback_texto):
    """Genera un archivo PDF con formato profesional e identificadores explícitos."""
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
        title="Informe de Evaluación - Retroalimentación",
        author=profesor
    )
    
    styles = getSampleStyleSheet()
    
    estilo_titulo = ParagraphStyle('TituloDoc', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor('#1E293B'))
    estilo_subtitulo = ParagraphStyle('SubtituloDoc', parent=styles['Heading2'], fontSize=12, leading=16, textColor=colors.HexColor('#475569'))
    estilo_body = ParagraphStyle('CuerpoDoc', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor('#0F172A'))
    
    story = []
    
    story.append(Paragraph("Informe de Evaluación y Retroalimentación", estilo_titulo))
    story.append(Paragraph(f"<b>Evaluador/a:</b> {profesor}", estilo_subtitulo))
    story.append(Spacer(1, 15))
    
    tabla_datos = [
        [Paragraph("<b>Calificación Final:</b>", estilo_body), Paragraph(str(nota), estilo_body)],
        [Paragraph("<b>Puntaje Obtenido:</b>", estilo_body), Paragraph(str(puntaje), estilo_body)]
    ]
    
    t = Table(tabla_datos, colWidths=[150, 350])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("<b>Retroalimentación Detallada:</b>", estilo_subtitulo))
    story.append(Spacer(1, 8))
    
    lineas_feedback = feedback_texto.split('\n')
    for linea in lineas_feedback:
        if linea.strip():
            linea_pdf = linea.replace('**', '<b>').replace('**', '</b>').replace('*', '•')
            story.append(Paragraph(linea_pdf, estilo_body))
            story.append(Spacer(1, 4))
            
    doc.build(story)
    buffer.seek(0)
    return buffer

# ------------------------------------------------------------------------------
# 5. GESTIÓN DEL REGISTRO LOCAL CSV Y EXCEL
# ------------------------------------------------------------------------------
def guardar_en_registro(profesor, nota, puntaje):
    """Registra la evaluación en el archivo CSV local."""
    nuevo_registro = pd.DataFrame([{
        "Fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
        "Profesor": profesor,
        "Nota": nota,
        "Puntaje": puntaje
    }])
    
    if not os.path.exists(ARCHIVO_CSV):
        nuevo_registro.to_csv(ARCHIVO_CSV, index=False)
    else:
        nuevo_registro.to_csv(ARCHIVO_CSV, mode='a', header=False, index=False)

def cargar_registro():
    """Carga el historial ignorando líneas corruptas si existieran."""
    if os.path.exists(ARCHIVO_CSV):
        try:
            return pd.read_csv(ARCHIVO_CSV, on_bad_lines='skip')
        except Exception:
            return pd.DataFrame(columns=["Fecha", "Profesor", "Nota", "Puntaje"])
    return pd.DataFrame(columns=["Fecha", "Profesor", "Nota", "Puntaje"])

# ------------------------------------------------------------------------------
# 6. INTERFAZ STREAMLIT
# ------------------------------------------------------------------------------
st.title("Corrector y Retroalimentador de Pruebas")

col1, col2 = st.columns([1, 1])

# --- COLUMNA 1: ENTRADAS DE EVALUACIÓN ---
with col1:
    st.subheader("1. Entradas de Evaluación")
    
    nombre_profesor = st.text_input("Nombre del Profesor/a", value="Augusth")
    
    st.markdown("**Sube la rúbrica (Imagen o PDF)**")
    archivo_rubrica = st.file_uploader("Subir Rúbrica", type=["pdf", "png", "jpg", "jpeg"], label_visibility="collapsed")
    
    texto_rubrica = st.text_area("O pega el texto de la rúbrica aquí si no tienes archivo:", height=100)
    
    st.markdown("**Sube la prueba del alumno (PDF o Imagen)**")
    archivo_prueba = st.file_uploader("Subir Prueba", type=["pdf", "png", "jpg", "jpeg"], label_visibility="collapsed")
    
    btn_evaluar = st.button("Evaluar y Calificar", type="primary", use_container_width=True)

# --- COLUMNA 2: RESULTADOS Y PROCESAMIENTO ---
with col2:
    st.subheader("2. Resultado del Alumno")
    
    if btn_evaluar:
        if not archivo_rubrica and not texto_rubrica.strip():
            st.error("Por favor, proporciona una rúbrica (sube un archivo o escribe el texto).")
        elif not archivo_prueba:
            st.error("Por favor, sube el archivo de la prueba del alumno.")
        else:
            with st.spinner("Procesando evaluación... Evaluando redundancia de servidores."):
                try:
                    contenidos_gemini = []
                    texto_groq = ""
                    
                    # PROCESAMIENTO DE RÚBRICA
                    if archivo_rubrica:
                        bytes_rubrica = archivo_rubrica.read()
                        contenidos_gemini.append(types.Part.from_bytes(data=bytes_rubrica, mime_type=archivo_rubrica.type))
                        contenidos_gemini.append("Rúbrica de evaluación provista en el archivo adjunto arriba.")
                        
                        # Extracción para Groq si es PDF
                        if archivo_rubrica.type == "application/pdf":
                            txt = extraer_texto_pdf(bytes_rubrica)
                            texto_groq += f"\n--- TEXTO DE RÚBRICA ---\n{txt}\n"
                        else:
                            texto_groq += "\n--- RÚBRICA ---\n(Rúbrica proporcionada en imagen)\n"
                    else:
                        contenidos_gemini.append(f"Rúbrica de evaluación en texto:\n{texto_rubrica}")
                        texto_groq += f"\n--- TEXTO DE RÚBRICA ---\n{texto_rubrica}\n"
                    
                    # PROCESAMIENTO DE PRUEBA
                    bytes_prueba = archivo_prueba.read()
                    contenidos_gemini.append(types.Part.from_bytes(data=bytes_prueba, mime_type=archivo_prueba.type))
                    contenidos_gemini.append("Prueba resuelta por el estudiante provista en el archivo adjunto arriba.")
                    
                    if archivo_prueba.type == "application/pdf":
                        txt_p = extraer_texto_pdf(bytes_prueba)
                        texto_groq += f"\n--- RESPUESTAS DEL ESTUDIANTE ---\n{txt_p}\n"
                    else:
                        texto_groq += "\n--- RESPUESTAS DEL ESTUDIANTE ---\n(Respuestas en formato imagen)\n"
                    
                    instruccion_sistema = (
                        "Eres un asistente pedagógico experto en corrección de evaluaciones académicas. "
                        "Compara rigurosamente la prueba del alumno con la rúbrica entregada.\n\n"
                        "DEBES ESTRUCTURAR TU RESPUESTA OBLIGATORIAMENTE DE LA SIGUIENTE MANERA:\n"
                        "1. En la primera línea escribe solo: NOTA: [Valor de la nota final de 1.0 a 7.0 o de 0 a 100]\n"
                        "2. En la segunda línea escribe solo: PUNTAJE: [Puntaje obtenido / Puntaje total]\n"
                        "3. A partir de la tercera línea, entrega el FEEDBACK FORMATIVO detallado: fortalezas, "
                        "errores cometidos, justificación de puntaje criterio por criterio y sugerencias concretas de mejora."
                    )
                    
                    # Ejecución multiservidor con failover
                    resultado_texto, servidor_usado = evaluar_con_ia_multiservidor(
                        contenidos_gemini=contenidos_gemini,
                        texto_prompts_groq=texto_groq,
                        system_instruction=instruccion_sistema
                    )
                    
                    # Procesamiento de la respuesta
                    lineas = [l.strip() for l in resultado_texto.split('\n') if l.strip()]
                    nota_extraida = "N/A"
                    puntaje_extraido = "N/A"
                    idx_inicio_feedback = 0
                    
                    for i, l in enumerate(lineas):
                        if l.upper().startswith("NOTA:"):
                            nota_extraida = l.split(":", 1)[1].strip()
                        elif l.upper().startswith("PUNTAJE:"):
                            puntaje_extraido = l.split(":", 1)[1].strip()
                            idx_inicio_feedback = i + 1
                    
                    feedback_completo = "\n\n".join(lineas[idx_inicio_feedback:]) if idx_inicio_feedback > 0 else resultado_texto
                    
                    # Guardar registro
                    guardar_en_registro(nombre_profesor, nota_extraida, puntaje_extraido)
                    
                    # Interfaz de resultados
                    st.success(f"Evaluación procesada exitosamente usando: **{servidor_usado}**")
                    
                    m1, m2 = st.columns(2)
                    m1.metric("Nota Final", nota_extraida)
                    m2.metric("Puntaje", puntaje_extraido)
                    
                    st.markdown("### Feedback Formativo")
                    st.markdown(feedback_completo)
                    
                    # Generación PDF
                    pdf_bytes = generar_reporte_pdf(
                        profesor=nombre_profesor,
                        nota=nota_extraida,
                        puntaje=puntaje_extraido,
                        feedback_texto=feedback_completo
                    )
                    
                    st.download_button(
                        label="📄 Descargar Informe PDF",
                        data=pdf_bytes,
                        file_name=f"Informe_Evaluacion_{nombre_profesor}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                    
                except Exception as ex:
                    st.error(f"Error durante el proceso: {ex}")

# ------------------------------------------------------------------------------
# 7. PLANILLA CONSOLIDADA DE EVALUACIONES
# ------------------------------------------------------------------------------
st.markdown("---")
st.subheader("Planilla Consolidada de Evaluaciones")

df_registro = cargar_registro()

if not df_registro.empty:
    st.dataframe(df_registro, use_container_width=True)
    
    buffer_excel = io.BytesIO()
    with pd.ExcelWriter(buffer_excel, engine='openpyxl') as writer:
        df_registro.to_excel(writer, index=False, sheet_name='Calificaciones')
    buffer_excel.seek(0)
    
    st.download_button(
        label="📊 Exportar Planilla a Excel",
        data=buffer_excel,
        file_name="registro_calificaciones.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.info("Aún no hay calificaciones registradas. Aparecerán automáticamente al evaluar.")