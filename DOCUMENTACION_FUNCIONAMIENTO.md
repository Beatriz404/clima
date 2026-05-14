La aplicación Clima Agrícola El Salvador está diseñada como un servicio web estructurado.
El sistema cumple con el propósito de centralizar, procesar y enriquecer datos meteorológicos orientados a la toma de decisiones en el sector agrícola nacional.

Las capacidades núcleo del sistema comprenden:

1. Ingesta de Datos Numéricos, es decir, consumo automatizado de pronósticos e históricos climáticos desde la API externa pública Open-Meteo.
2. Post-procesamiento Analítico: Aplicación de un modelo de ajuste (basado en aprendizaje automático o reglas heurísticas) sobre las variables de temperatura y probabilidad de precipitación.
3. Lógica de Dominio Agrícola: Evaluación de ventanas de aptitud para la siembra y determinación de riesgos agroclimáticos críticos (tales como sequías prolongadas o excesos hídricos) mediante módulos nativos en Python.
4. Persistencia de Datos: Almacenamiento relacional de consultas y recomendaciones en un motor SQLite gestionado a través del ORM SQLAlchemy.
5. Entrega de Interfaz de Usuario: Servicio del frontend autónomo 
6. Agregación de Información Institucional: Exposición de una API pública documentada que actúa como un extractor superficial y normalizador del portal web oficial del Ministerio de Medio Ambiente y Recursos Naturales (MARN) de El Salvador, operando de manera independiente y aditiva al flujo principal de Open-Meteo.

 2. Arquitectura de Directorios y Componentes

El repositorio se organiza de acuerdo con una arquitectura modular que segrega las responsabilidades de configuración, ruteo, persistencia y lógica de negocio:
Ruta del Componente	Responsabilidad Técnica	Alcance sobre Open-Meteo / Sequía
app/main.py	Punto de entrada del servicio. Define la instancia de FastAPI, políticas CORS, montaje de archivos estáticos y registro de enrutadores HTTP.	Registra los endpoints /forecast, /adjusted, /planting, /insights que consumen Open-Meteo. El endpoint /insights calcula la variación porcentual de lluvia (sequía).
app/configuracion.py	Gestión de variables de entorno y tipado de configuraciones globales mediante pydantic-settings.	Define las URLs base de Open-Meteo (api_open_meteo_base, api_open_meteo_archivo_base) y la zona horaria.
app/esquemas.py	Definición de modelos de datos Pydantic. Establece los contratos de entrada y salida (DTOs) de la API.	Define RespuestaInsights que incluye el campo comparacion_anual.variacion_porcentual (el valor real de sequía).
app/services/open_meteo.py	Cliente HTTP asíncrono encargado del consumo de los endpoints de forecast e histórico de Open-Meteo.	Fuente principal de datos: Obtiene temperaturas, lluvia, humedad y datos históricos (para comparación anual). Sin este archivo, no hay cálculo de sequía.
app/services/agricultura.py	Motor de reglas de negocio para la determinación de aptitud de siembra.	Utiliza datos de Open-Meteo (temperatura ajustada, lluvia, probabilidad) para decidir si sembrar o no.
app/services/analitica_agricola.py	Módulo de análisis avanzado: agregación de métricas de lluvia mensual, cálculo de riesgos y despacho de notificaciones.	Contiene riesgo_sequia() y lluvia_por_mes(), que procesan los datos de Open-Meteo para determinar niveles de sequía.
app/services/ajuste_ml.py	Pipeline de ejecución del modelo predictivo o heurístico para el ajuste de variables climáticas diarias.	Ajusta las temperaturas y probabilidades de lluvia provenientes de Open-Meteo usando un modelo ML (Scikit-learn).
app/services/marn.py	Componente de integración proxy para la redirección de consultas hacia servicios externos integrados.	No usa Open-Meteo. Solo redirige consultas al backend intermedio MARN. No participa en el cálculo de sequía.
app/services/marn_intermedio.py	Lógica de extracción, filtrado y normalización del HTML del portal del MARN hacia un formato JSON v1 estable.	No usa Open-Meteo. Solo extrae datos del portal MARN. No participa en el cálculo de sequía.
app/base_datos.py	Configuración del motor de base de datos, sesiones y ciclo de vida de las conexiones con SQLAlchemy.	Almacena registros históricos de pronósticos y recomendaciones, pero no influye en el cálculo en vivo de la variación de sequía.
app/modelos.py	Declaración de los modelos del ORM que definen el esquema de las tablas en SQLite.	Define RegistroClimatico (guarda datos de Open-Meteo) y RecomendacionSiembra.
frontend/index.html	SPA (Single Page Application) construida en HTML/CSS/JS nativo que expone el tablero de control, mapas interactivos y la integración de la API MARN.	Problema identificado: Muestra un texto fijo -41% en lugar de consumir el valor real de variacion_porcentual del endpoint /insights.
tests/	Suite de pruebas automatizadas unitarias y de integración ejecutadas bajo el framework pytest.	Debe incluir pruebas que verifiquen que variacion_porcentual se calcula correctamente con datos mock de Open-Meteo.

3. Parámetros de Configuración (`app/configuracion.py`)

La suite de configuraciones se gestiona de forma centralizada, permitiendo la inyección de valores mediante variables de entorno o archivos de configuración `.env`.

3.1 Proveedor Climático Principal (Open-Meteo)

 `API_OPEN_METEO_BASE`: Establece la URL base para el servicio de pronósticos (Valor por defecto: `https://api.open-meteo.com/v1`).
 `API_OPEN_METEO_ARCHIVO_BASE`: Define el endpoint para la consulta de registros históricos (Valor por defecto: `https://archive-api.open-meteo.com/v1`).
 `ZONA_HORARIA`: Cadena de texto que define la región horaria de la aplicación (Valor por defecto: `America/El_Salvador`).

3.2 Persistencia y Modelos Estadísticos

 `BASE_DATOS_URL`: Cadena de conexión para el motor de base de datos relacional (Valor por defecto: `sqlite:///./clima_agricola.db`).
 `RUTA_MODELO_ML`: Ruta local del sistema de archivos hacia el artefacto serializado (`.pkl`) que contiene el modelo ajustador de Machine Learning.

3.3 Proxy de Complemento MARN

 `MARN_COMPLEMENTO_URL`: Dirección URL de destino. Al ser configurada, el endpoint `POST /marn/complemento` despacha una petición GET hacia dicha localización inyectando parámetros geográficos (`latitud`, `longitud`, `altitud`) y encapsulando el JSON resultante.
 `MARN_API_TOKEN`: Mecanismo opcional de autenticación. Si posee un valor asignado, se adjunta automáticamente en la cabecera HTTP bajo el estándar `Authorization: Bearer <TOKEN>`.

> Patrón de Arquitectura Recomendado: Se sugiere apuntar `MARN_COMPLEMENTO_URL` de manera reflexiva hacia el endpoint de la propia aplicación:
> `https://<dominio-aplicacion>/api/v1/nacional/marn/resumen`
> Esto permite que los clientes del método heredado `POST /marn/complemento` se beneficien del nuevo agregador nacional sin incurrir en duplicidad de lógica o de servidores.

3.4 Origen de Datos del Portal MARN e Intermedio

 `MARN_PORTAL_BASE_URL`: URL base del sitio web institucional (Valor por defecto: `https://www.marn.gob.sv/`).
 `MARN_PORTAL_PATH`: Segmento de ruta específico del portal (por ejemplo, subsecciones de meteorología). Si se omite, se procesará la raíz del dominio configurado.
 `MARN_INTERMEDIO_MODO`: Selector de comportamiento para la capa de extracción:
 `auto` (Predeterminado): Activa la descarga en tiempo real del HTML del portal y ejecuta el algoritmo de parsing.
 `demo`: Omite la salida a red y entrega un set de datos estático, ideal para entornos aislados o de pruebas.
 `off`: Deshabilita por completo las consultas externas, retornando un estado explícito de desactivación.

4. Catálogo de la API REST: Endpoints Originales

Los siguientes endpoints operan bajo contratos inmutables. Todos esperan en el cuerpo de la petición un objeto JSON estructurado bajo el esquema `SolicitudClima`, el cual valida rangos geográficos estrictamente delimitados para el territorio de El Salvador.

4.1 `POST /forecast`

Procesa las coordenadas enviadas y delega la captura de datos al cliente de Open-Meteo. Retorna una colección estructurada por días que desglosa temperaturas máximas/mínimas, volumen de precipitación y humedad relativa.

4.2 `POST /adjusted`

Ejecuta de manera secuencial la consulta meteorológica y el algoritmo de ajuste ML. Cada transacción exitosa persiste de forma automática un registro histórico dentro de la tabla `RegistroClimatico`.

4.3 `POST /planting`

Consolida las métricas del pronóstico ajustado y somete los datos a las reglas de negocio declaradas en `evaluar_dia_siembra`. Genera recomendaciones indexadas por fecha y las almacena en la tabla `RecomendacionSiembra`.

4.4 `POST /insights`

Orquesta múltiples capas analíticas: procesamiento climáticos preliminares, identificación de amenazas críticas, generación de resúmenes descriptivos de microclima y cálculo comparativo de precipitación anual acumulada frente al año previo.

4.5 `GET /`

Controlador de enrutamiento raíz. Resuelve y sirve el archivo estático `frontend/index.html` si está disponible en el despliegue; de lo contrario, provee un objeto JSON que detalla el estado operacional del microservicio.

4.6 Recursos Estáticos (`GET /static/...`)

Expone la ruta de montaje para activos fijos como estilos CSS o dependencias JavaScript del frontend histórico.


5. Arquitectura de la Capa MARN (Integración y API Documentada)

5.1 Propósito Técnico

La capa MARN se incorpora con el objetivo de proveer un agregador semántico del portal web institucional. Esta funcionalidad está completamente desacoplada de las métricas cuantitativas provistas por Open-Meteo, garantizando alta cohesión y bajo acoplamiento en el código. Se expone como un servicio de carácter estrictamente informativo, no vinculante y complementario.

5.2 Especificación del Endpoint Público Documentado

El servicio publica el recurso `GET /api/v1/nacional/marn/resumen`, indexado bajo la etiqueta «Nacional MARN (API pública documentada)» en la interfaz interactiva de Swagger UI (`/docs`).

Parámetros de Consulta (Query Parameters)

 `latitud` (Obligatorio): Coordenada decimal validada dentro del marco geográfico nacional.
 `longitud` (Obligatorio): Coordenada decimal validada.
 `altitud` (Opcional - Defecto: `650`): Utilizado exclusivamente para fines de contextualización del cliente, dado que el documento HTML extraído es uniforme a nivel país.

Estructura de Respuesta (`ResumenMarnApiV1`)

El contrato de salida garantiza estabilidad mediante el siguiente esquema JSON:

 `schema_version`: Cadena de control de versión de la API (Fijo: `"1.0"`).
 `generado_en`: Sello de tiempo en formato ISO 8601 UTC.
 `consulta`: Objeto de eco que refleja los parámetros geográficos provistos.
 `fuente_oficial`: Declaración de origen de datos institucional.
 `modo`: Indicador de ejecución del servicio (`portal` | `demo` | `off` | `no_disponible`).
 `url_portal_consultado`: Dirección URL exacta sobre la cual el backend efectuó la petición HTTP.
 `items`: Matriz de objetos `ItemMarnExtraccion`, donde cada elemento se compone de:
 `tipo`: Categoría del elemento (`enlace` | `texto` | `aviso`).
 `titulo`: Rótulo de la sección o hipervínculo identificado.
 `detalle`: Texto extendido o descriptivo asociado.
 `url`: Enlace absoluto normalizado.


 `nota_metodologica`: Texto legal y técnico que delimita la responsabilidad y alcances de la extracción de datos.

5.3 Flujo de Ejecución Interna (`app/services/marn_intermedio.py`)

Cuando se invoca el endpoint en modo automático (`auto`), la aplicación realiza los siguientes pasos lógicos:

[Cliente] -> GET /api/v1/nacional/marn/resumen
                     |
                     v
       ¿MARN_INTERMEDIO_MODO?
         /         |         \
   (off) /   (demo)│          \ (auto)
        /          │           \
       v           v            v
[Retorna Vacío] [Retorna Mock] [Petición HTTP GET via httpx]
                                        |
                                        v
                               [Limpieza de HTML]
                           (Remoción <script> y <style>)
                                        |
                                        v
                            [Ejecución de Regex]
                        (Búsqueda de términos clave)
                                        |
                                        v
                           [Normalización de Enlaces]
                             (Resolución via urljoin)
                                        |
                                        v
                                 [Respuesta JSON]


1. Resolución de Destino: Ensambla la ruta de red utilizando la función interna `construir_url_portal` pasándole las variables globales configuradas.
2. Validación de Modos Cortocircuito: Si el modo es `off` o `demo`, se interrumpe el flujo de red inmediatamente devolviendo una estructura predecible vacía o simulada, respectivamente.
3. Consumo Asíncrono Segurizado: Realiza una petición GET mediante el cliente HTTP `httpx`. Configura cabeceras estandarizadas de `User-Agent` para identificarse ante el servidor de destino y acota tiempos límite de espera (timeouts) para prevenir el bloqueo de hilos de ejecución.
4. Sanitización del Árbol DOM: Elimina de manera agresiva etiquetas no textuales como `<script>` y `<style>` del cuerpo de la respuesta HTML para mitigar el ruido en el procesamiento.
5. Extracción por Patrones Semánticos: La función interna `extraer_items_de_portal_marn` aplica expresiones regulares destinadas a capturar selectores de hipervínculos (`<a href="...">`). Filtra y prioriza los elementos cuyas anclas o textos contengan palabras clave asociadas a fenómenos meteorológicos (ej. clima, meteor, lluvia, pronóstico). Las rutas relativas son mapeadas a absolutas usando la utilidad `urljoin`.
6. Estrategia de Resiliencia (Fallback): Si el análisis estructural no arroja coincidencias, el sistema intenta capturar la etiqueta `<title>` global de la página web para poblar la respuesta. En caso de fallas de conectividad o cambios drásticos en la infraestructura del portal objetivo, el sistema captura la excepción, conmuta el estado de la propiedad `modo` a `no_disponible` e inyecta un ítem de tipo `aviso` detallando la incidencia de forma controlada, evitando la interrupción total del ecosistema de la app.

5.4 Comportamiento del Proxy Complementario (`app/services/marn.py`)

Mantiene soporte para el flujo tradicional mediante `POST /marn/complemento`. Si detecta la ausencia de la variable `MARN_COMPLEMENTO_URL`, responde de forma transparente con un indicador booleano `disponible: false`. En escenario positivo, actúa como pasarela HTTP e inserta la respuesta íntegra dentro de la clave `datos`. El estado de esta ruta se expone de forma explícita mediante el endpoint de diagnóstico `GET /marn/estado`.


6. Interfaz Web Frontal (`frontend/index.html`)

El frontend está estructurado como un componente unificado de página única que consume los servicios del backend de forma dinámica.

### 6.1 Integración del Consumo del Portal MARN en la UI

La interfaz gráfica de usuario procesa la información provista por el canal institucional del MARN bajo estrictas condiciones de contexto de red:

 Identificación de Origen: La aplicación inicializa un proceso JavaScript que se dispara de manera reactiva durante la invocación de la rutina de refresco del cuadro de mando (`refreshDashboard()`). Esta acción se ejecuta toda vez que el usuario altera la posición del marcador en el componente de mapas (Leaflet).
 Invocación Relativa: El script efectúa una petición asíncrona (`fetch`) apuntando a la ruta `window.location.origin + "/api/v1/nacional/marn/resumen"`. Esto asegura el correcto paso de parámetros geográficos contextualizados al servidor que hospeda el backend.
 Renderizado Dinámico: La interfaz mapea el JSON de respuesta pintando en pantalla los estados del modo operativo, los enlaces externos funcionales provistos por el parser y los bloques informativos de la nota metodológica.
 Restricción del Protocolo Local (`file://`): Si un operador inicializa el archivo de la interfaz directamente en un navegador mediante el sistema de archivos local sin mediación de un servidor web, el mecanismo de seguridad del navegador restringe las llamadas asíncronas externas. El código JS intercepta esta condición de entorno, inhabilitando la tarjeta interactiva del MARN y renderizando en su lugar un hipervínculo directo hacia la dirección web institucional del ministerio.

6.2 Separación de Capas de Datos en el Panel Principal

El cuadro de mando mantiene una estricta delimitación visual y técnica de las fuentes de información:

 Las componentes analíticas cuantitativas (gráficas de Chart.js, indicadores térmicos, volúmenes hídricos e índices de siembra) se resuelven de forma exclusiva mediante el procesamiento local del cliente web (y su posterior comunicación con las rutas numéricas de Open-Meteo).
 La sección destinada al MARN actúa de forma puramente agregativa, sirviendo como un hub de consulta institucional que no interfiere ni modifica los cálculos analíticos agrícolas del sistema central.


7. Capa de Persistencia de Datos

El ciclo de vida del esquema de base de datos se autogestiona en el arranque del microservicio web mediante el llamado explícito de la función `Base.metadata.create_all` provista por SQLAlchemy sobre la instancia del archivo SQLite. Las operaciones de escritura y mutación del estado de las tablas se concentran de forma mayoritaria en la ejecución exitosa de las llamadas HTTP dirigidas a los endpoints `/adjusted` y `/planting`.


8. Estrategia de Pruebas y Calidad de Código

El repositorio cuenta con un arnés de pruebas automatizadas localizado en la carpeta `tests/`. La validación del sistema se realiza mediante la ejecución del comando:


El alcance de la cobertura de pruebas se distribuye de la siguiente manera:

 `test_agricultura.py`: Valida de forma determinista las matrices de decisión y la lógica marginal del motor de aptitud de siembra.
 `test_marn.py`: Verifica el comportamiento por defecto y los códigos de respuesta del módulo proxy ante la falta de variables de entorno configuradas.
 `test_marn_intermedio.py`: Evalúa los algoritmos de parseo de código HTML, inyectando respuestas simuladas (mocks) para certificar la correcta estructuración del esquema JSON final ante diferentes variantes de páginas web.


9. Criterios de Operación y Despliegue en Producción

Para el despliegue del sistema (por ejemplo, en plataformas PaaS como Render), el equipo de operaciones debe observar los siguientes lineamientos:

1. Inyección de Entorno: Proveer las cadenas de conexión correctas correspondientes a las instancias de producción para la base de datos y los parámetros base de las APIs meteorológicas.
2. Mitigación de Riesgos en Entornos Corporativos: Si las políticas de infraestructura prohíben la ejecución de web scraping o llamadas externas arbitrarias desde los servidores de producción, se debe forzar el comportamiento de la capa MARN configurando la variable `MARN_INTERMEDIO_MODO=demo` o `MARN_INTERMEDIO_MODO=off`.
3. Encadenamiento de Proxies: Para habilitar el reenvío transparente del módulo proxy hacia la nueva API pública documentada, configure la variable de la siguiente forma:
4. Cumplimiento de Buenas Prácticas de Red: Previo a establecer el modo de ejecución en `auto` dentro de entornos con alta concurrencia hídrica de usuarios, es imperativo analizar los términos y condiciones de uso del portal gubernamental, garantizando no incurrir en violaciones de tasas de transferencia (rate limiting).


10. Compilación y Generación de Entregables Impresos

El proyecto incluye un pipeline automatizado de generación de documentación técnica legible por humanos localizado en la raíz. Para generar copias físicas o archivos portables del presente manual de funcionamiento, ejecute la siguiente secuencia de comandos en la terminal del sistema:

 Formatos Resultantes del Pipeline:

 `DOCUMENTACION_FUNCIONAMIENTO_print.html`: Archivo HTML optimizado con hojas de estilo CSS para impresión (print-media stylesheets). Su flujo de trabajo idóneo requiere su apertura en navegadores basados en Chromium (Chrome/Edge), seleccionando la opción Imprimir → Guardar como PDF para obtener una salida con alta fidelidad tipográfica.
 `DOCUMENTACION_FUNCIONAMIENTO.pdf`: Documento PDF generado de manera directa por el intérprete de Python, condicionado a la presencia de la librería `fpdf2` y la disponibilidad de fuentes TrueType convencionales dentro del entorno de ejecución.
