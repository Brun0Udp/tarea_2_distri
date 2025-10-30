SISTEMA DE Q&A CON LLM Y STREAMING DE EVENTOS
DESCRIPCIÓN
Sistema distribuido de preguntas y respuestas que utiliza un LLM para generar respuestas, con validación de calidad mediante scoring y reintento automático. Arquitectura basada en
eventos con Apache Kafka.
ARQUITECTURA
Usuario
|
v
Storage API (FastAPI)
|
+---> PostgreSQL (caché de resultados)
|
+---> Kafka Topics:
|
+---> [preguntas] ---------> LLM Worker
| |
| v
| [llm_respuestas] ---> Flink Job
| |
| v
+-------- [preguntas.retry] <------- (score < threshold)
| |
+-------- [dlq] <-------------- (errores finales) |
| v
+-------- [resultados_validados] <---- (score >= threshold)
|
v
Storage API ---> PostgreSQL



COMPONENTES

1. STORAGE API (storage_api/)
API REST punto de entrada
Gestiona caché en PostgreSQL
Publica preguntas a Kafka
Endpoints:
GET /health - Health check
POST /query - Enviar pregunta (con caché)
POST /persist - Persistir resultados

2. LLM WORKER (llm_worker/)
Procesa preguntas usando LLM
Soporta OpenAI o mock
Manejo de errores con reintentos
Backoff exponencial
Errores manejados:
overload - Sobrecarga del servicio
quota - Límite de cuota excedido

3. FLINK JOB (flink_job/)
Valida calidad de respuestas
Scoring Jaccard entre pregunta/respuesta
Decisión: aceptar, reintentar o rechazar
Lógica:
score >= 0.62 -> Acepta y persiste
score < 0.62 y attempts < 2 -> Reintenta
attempts >= 2 -> Envía a DLQ

4. TRAFFIC GENERATOR (traffic_gen/)
Generador de tráfico para pruebas
Configurable: QPM y total de queries

Inicio Rapido
Con la descarga de los codigos del repositorio git.
Abrir terminal de la carpeta donde se guardo o clono el repositorio.
Correr comando:

     run start-script.sh

Y esperar hasta que termine. 
Con eso el codigo estara ejecutandose.

FLUJO COMPLETO DE PROCESAMIENTO
1. Usuario envía pregunta -> Storage API
2. Storage API verifica caché en PostgreSQL
3. Si no existe en caché: a. Publica a topic 'preguntas' b. Publica a topic 'llm.requests'
4. LLM Worker consume de 'preguntas': a. Llama a LLM (OpenAI o mock) b. Si hay error de overload/quota -> reintenta con backoff c. Si falla definitivamente -> envía a DLQ d. Si
exitoso -> publica respuesta a 'llm_respuestas'
5. Flink Job consume de 'llm_respuestas': a. Calcula score Jaccard entre pregunta y respuesta b. Si score >= 0.62:
Publica a 'resultados_validados' c. Si score < 0.62 y attempts < 2:
Incrementa contador de intentos
Publica a 'preguntas' (reintento) d. Si attempts >= 2:
Envía a DLQ (rechazado por bajo score)
6. Storage API consume de 'resultados_validados': a. Persiste en PostgreSQL b. Disponible en caché para futuras consultas


MONITOREO Y DEBUG

-VERIFICAR POSTGRESQL 

  docker exec -it postgres psql -U user -d yahoo_answers_db SELECT id, question, score, attempts FROM qa_results ORDER BY decided_at DESC LIMIT 10;


-MONITOREAR KAFKA TOPICS

Ver mensajes en DLQ
  docker exec -it kafka /opt/kafka/bin/kafka-console-consumer.sh
  --bootstrap-server kafka:9092
  --topic dlq
  --from-beginning

Ver respuestas validadas
  docker exec -it kafka /opt/kafka/bin/kafka-console-consumer.sh
  --bootstrap-server kafka:9092
  --topic resultados_validados
  --from-beginning

Listar todos los topics
  docker exec -it kafka /opt/kafka/bin/kafka-topics.sh
  --bootstrap-server kafka:9092
  --list

-LOGS DE SERVICIOS

Ver todo el tráfico procesado
  docker-compose logs -f traffic_gen

Ver decisiones de scoring
  docker-compose logs -f flink_job

Ver respuestas del LLM
  docker-compose logs -f llm_worker

Ver actividad de Storage API
  docker-compose logs -f storage_api


ESTRUCTURA DEL PROYECTO
. ├── common/ 
│ └── schema.py # Modelos de datos compartidos 
├── flink_job/ 
│ ├── Dockerfile 
│ ├── requirements.txt 
│ └── job.py # Procesador de scoring y validación
├── llm_worker/ 
│ ├── Dockerfile 
│ ├── requirements.txt 
│ └── worker.py # Worker que llama al LLM 
├── sql/ 
│ └── init.sql # Schema de PostgreSQL 
├── storage_api/ 
│
├── Dockerfile 
│ ├── requirements.txt 
│ └── main.py # API REST 
├── traffic_gen/ 
│ ├── Dockerfile 
│ ├── requirements.txt 
│ └── gen.py # Generador de tráfico 
├── dockercompose.yml # Orquestación de servicios 
├── start-script.sh # Script de inicio (a crear) 
└── README.txt # Este archivo

