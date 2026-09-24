import io
import os
import time
import random
import pandas as pd
import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import APIError
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

# Recuperación segura de la API Key desde Streamlit Secrets
api_key = st.secrets.get("GEMINI_API_KEY")
if not api_key:
    st.error("Error: No se ha configurado 'GEMINI_API_KEY' en los Secrets de Streamlit.")
    st.stop()

# Inicialización del cliente oficial de Google GenAI
client = genai.Client(api_key=api_key)

MODELO_PRINCIPAL = "gemini-3.6-flash"
MODELO_RESPALDO = "gemini-2.5-flash"
ARCHIVO_CSV = "registro_calificaciones.csv"

# ------------------------------------------------------------------------------
# 2. FUNCIONES CON REINTENTOS ESCALONADOS (MANEJO ROBUSTO DE ERROR 503)
# ------------------------------------------------------------------------------
def generar_contenido_con_reintentos(client, contenidos, system_instruction, max_reintentos=5):
    """
    Ejecuta peticiones a la API con reintentos escalonados ante errores 503 o 429.
    Utiliza backoff exponencial con jitter y modelo de respaldo si la saturación persiste.
    """
    modelos = [MODELO_PRINCIPAL, MODELO_RESPALDO]
    
    for modelo in modelos:
        for intento in range(1, max_reintentos + 1):
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2
                )
                
                response = client.models.generate_content(
                    model=modelo,
                    contents=contenidos,
                    config=config
                )
                return response.text
            
            except APIError as e:
                # Código 503 (UNAVAILABLE) o 429 (RESOURCE_EXHAUSTED / RATE LIMIT)
                es_saturacion = (e.code == 503 or e.code == 429 or "UNAVAILABLE" in str(e) or "high demand" in str(e))
                
                if es_saturacion and intento < max_reintentos:
                    # Tiempo de espera exponencial con fluctuación aleatoria (jitter)
                    tiempo_espera = (2 ** intento) + random.uniform(0.5, 1.5)
                    st.toast(
                        f"Servidor ocupado. Reintentando ({intento}/{max_reintentos}) en {tiempo_espera:.1f}s...", 
                        icon="⏳"
                    )
                    time.sleep(tiempo_espera)
                elif es_saturacion and modelo != modelos[-1]:
                    # Cambia al modelo de respaldo si el principal falla todos sus reintentos
                    st.toast(f"Cambiando a modelo de contingencia por alta demanda...", icon="🔄")
                    break
                else:
                    # Si no es un error de saturación recuperable o agotó todos los modelos, lanza la excepción
                    raise e
            except Exception as e:
                raise e
                
    raise RuntimeError("No se pudo completar la solicitud debido a una saturación prolongada en los servidores de IA.")

# ------------------------------------------------------------------------------
# 3. GENERACIÓN DE REPORTES EN PDF (REPORTLAB)
# ------------------------------------------------------------------------------
def generar_reporte_pdf(profesor, nota, puntaje, feedback_texto):
    """Genera un archivo PDF con formato limpio e identificadores correctos."""
    buffer = io.BytesIO()
    
    # Documento con metadatos explícitos
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
    
    # Estilos personalizados
    estilo_titulo = ParagraphStyle('TituloDoc', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor('#1E293B'))
    estilo_subtitulo = ParagraphStyle('SubtituloDoc', parent=styles['Heading2'], fontSize=12, leading=16, textColor=colors.HexColor('#475569'))
    estilo_body = ParagraphStyle('CuerpoDoc', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor('#0F172A'))
    
    story = []
    
    # Encabezado
    story.append(Paragraph("Informe de Evaluación y Retroalimentación", estilo_titulo))
    story.append(Paragraph(f"<b>Evaluador/a:</b> {profesor}", estilo_subtitulo))
    story.append(Spacer(1, 15))
    
    # Resumen de Resultados
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
    
    # Detalle del Feedback Formativo
    story.append(Paragraph("<b>Retroalimentación Detallada:</b>", estilo_subtitulo))
    story.append(Spacer(1, 8))
    
    # Procesar saltos de línea para el PDF
    lineas_feedback = feedback_texto.split('\n')
    for linea in lineas_feedback:
        if linea.strip():
            # Limpieza básica de Markdown para ReportLab Paragraph
            linea_pdf = linea.replace('**', '<b>').replace('**', '</b>').replace('*', '•')
            story.append(Paragraph(linea_pdf, estilo_body))
            story.append(Spacer(1, 4))
            
    doc.build(story)
    buffer.seek(0)
    return buffer

# ------------------------------------------------------------------------------
# 4. GESTIÓN DEL REGISTRO LOCAL CSV / EXCEL
# ------------------------------------------------------------------------------
def guardar_en_registro(profesor, nota, puntaje):
    """Guarda los resultados acumulados en el archivo CSV local de forma segura."""
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
    """Lee el CSV histórico omitiendo líneas corruptas si existieran."""
    if os.path.exists(ARCHIVO_CSV):
        try:
            return pd.read_csv(ARCHIVO_CSV, on_bad_lines='skip')
        except Exception:
            return pd.DataFrame(columns=["Fecha", "Profesor", "Nota", "Puntaje"])
    return pd.DataFrame(columns=["Fecha", "Profesor", "Nota", "Puntaje"])

# ------------------------------------------------------------------------------
# 5. INTERFAZ Y FLUJO DE USUARIO (STREAMLIT)
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
        # Validaciones de entrada
        if not archivo_rubrica and not texto_rubrica.strip():
            st.error("Por favor, proporciona una rúbrica (sube un archivo o escribe el texto).")
        elif not archivo_prueba:
            st.error("Por favor, sube el archivo de la prueba del alumno.")
        else:
            with st.spinner("Procesando evaluación con Gemini IA... Esto puede tomar unos segundos."):
                try:
                    contenidos_ia = []
                    
                    # Preparación de la Rúbrica
                    if archivo_rubrica:
                        bytes_rubrica = archivo_rubrica.read()
                        contenidos_ia.append(types.Part.from_bytes(data=bytes_rubrica, mime_type=archivo_rubrica.type))
                        contenidos_ia.append("Rúbrica de evaluación provista en el archivo adjunto arriba.")
                    else:
                        contenidos_ia.append(f"Rúbrica de evaluación en texto:\n{texto_rubrica}")
                    
                    # Preparación de la Prueba
                    bytes_prueba = archivo_prueba.read()
                    contenidos_ia.append(types.Part.from_bytes(data=bytes_prueba, mime_type=archivo_prueba.type))
                    contenidos_ia.append("Prueba resuelta por el estudiante provista en el archivo adjunto arriba.")
                    
                    # Instrucciones de Evaluación del Sistema
                    instruccion_sistema = (
                        "Eres un asistente pedagógico experto en corrección de evaluaciones académicas. "
                        "Compara rigurosamente la prueba del alumno con la rúbrica entregada.\n\n"
                        "DEBES ESTRUCTURAR TU RESPUESTA OBLIGATORIAMENTE DE LA SIGUIENTE MANERA:\n"
                        "1. En la primera línea escribe solo: NOTA: [Valor de la nota final de 1.0 a 7.0 o de 0 a 100]\n"
                        "2. En la segunda línea escribe solo: PUNTAJE: [Puntaje obtenido / Puntaje total]\n"
                        "3. A partir de la tercera línea, entrega el FEEDBACK FORMATIVO detallado: fortalezas, "
                        "errores cometidos, justificación de puntaje criterio por criterio y sugerencias concretas de mejora."
                    )
                    
                    # Ejecución con reintentos para evitar fallos 503
                    resultado_texto = generar_contenido_con_reintentos(
                        client=client,
                        contenidos=contenidos_ia,
                        system_instruction=instruccion_sistema
                    )
                    
                    # Extracción simple de Nota, Puntaje y Feedback
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
                    
                    # Guardar automáticamente en CSV local
                    guardar_en_registro(nombre_profesor, nota_extraida, puntaje_extraido)
                    
                    # Mostrar métricas en la interfaz
                    m1, m2 = st.columns(2)
                    m1.metric("Nota Final", nota_extraida)
                    m2.metric("Puntaje", puntaje_extraido)
                    
                    st.markdown("### Feedback Formativo")
                    st.markdown(feedback_completo)
                    
                    # Generación y Botón de Descarga del PDF
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
# 6. PLANILLA CONSOLIDADA DE EVALUACIONES
# ------------------------------------------------------------------------------
st.markdown("---")
st.subheader("Planilla Consolidada de Evaluaciones")

df_registro = cargar_registro()

if not df_registro.empty:
    st.dataframe(df_registro, use_container_width=True)
    
    # Exportación limpia a Excel sin dependencias complejas extra
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