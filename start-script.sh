#!/bin/bash
# Script de inicio para Sistema de Q&A con LLM
# Verifica dependencias, configura el entorno e inicia todos los servicios


set -e  # Salir si cualquier comando falla

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Función para imprimir con color
print_color() {
    color=$1
    shift
    echo -e "${color}$@${NC}"
}

print_header() {
    echo ""
    print_color "$BLUE" "════════════════════════════════════════════════════════════"
    print_color "$BLUE" "  $1"
    print_color "$BLUE" "════════════════════════════════════════════════════════════"
    echo ""
}

print_success() {
    print_color "$GREEN" "✓ $1"
}

print_warning() {
    print_color "$YELLOW" "⚠ $1"
}

print_error() {
    print_color "$RED" "✗ $1"
}

print_info() {
    print_color "$BLUE" "ℹ $1"
}




# 1. VERIFICAR DEPENDENCIAS

print_header "VERIFICANDO DEPENDENCIAS"

# Verificar Docker
if ! command -v docker &> /dev/null; then
    print_error "Docker no está instalado"
    print_info "Instala Docker desde: https://docs.docker.com/get-docker/"
    exit 1
fi
print_success "Docker está instalado: $(docker --version)"

# Verificar Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    print_error "Docker Compose no está instalado"
    print_info "Instala Docker Compose desde: https://docs.docker.com/compose/install/"
    exit 1
fi

# Determinar comando de compose
if docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi
print_success "Docker Compose está instalado: $($COMPOSE_CMD version)"

# Verificar curl (para health checks)
if ! command -v curl &> /dev/null; then
    print_warning "curl no está instalado (opcional, para health checks)"
fi



# 2. VERIFICAR PUERTOS

print_header "VERIFICANDO PUERTOS DISPONIBLES"

check_port() {
    port=$1
    service=$2
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 || netstat -tuln 2>/dev/null | grep -q ":$port "; then
        print_warning "Puerto $port ($service) está en uso"
        return 1
    else
        print_success "Puerto $port ($service) está disponible"
        return 0
    fi
}

PORTS_OK=true
check_port 5432 "PostgreSQL" || PORTS_OK=false
check_port 8000 "Storage API" || PORTS_OK=false
check_port 8081 "Flink UI" || PORTS_OK=false
check_port 9092 "Kafka" || PORTS_OK=false

if [ "$PORTS_OK" = false ]; then
    echo ""
    read -p "Algunos puertos están en uso. ¿Continuar de todas formas? (s/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[SsYy]$ ]]; then
        print_error "Abortado por el usuario"
        exit 1
    fi
fi




# 3. CONFIGURAR API KEY DE OPENAI

print_header "CONFIGURACIÓN DE API KEY"

# Verificar si docker-compose.yml existe
if [ ! -f "docker-compose.yml" ]; then
    print_error "docker-compose.yml no encontrado"
    print_info "Asegúrate de estar en el directorio raíz del proyecto"
    exit 1
fi

# Verificar si hay API key configurada
CURRENT_KEY=$(grep -A 5 "llm_worker:" docker-compose.yml | grep "OPENAI_API_KEY:" | cut -d'"' -f2 | tr -d ' ')

if [ -z "$CURRENT_KEY" ] || [ "$CURRENT_KEY" = "your-api-key-here" ] || [[ "$CURRENT_KEY" == *"sk-proj-HX8VOGbaQF"* ]]; then
    print_warning "No hay API key de OpenAI configurada o es la clave de ejemplo"
    echo ""
    print_info "Opciones:"
    print_info "  1. Usar modo MOCK (sin API key real, genera respuestas de prueba)"
    print_info "  2. Ingresar API key de OpenAI"
    print_info "  3. Continuar con la configuración actual"
    echo ""
    read -p "Selecciona una opción (1/2/3): " -n 1 -r
    echo ""
    
    case $REPLY in
        1)
            print_info "Configurando modo MOCK..."
            # Cambiar USE_REAL_LLM a false
            if [[ "$OSTYPE" == "darwin"* ]]; then
                # macOS
                sed -i '' 's/USE_REAL_LLM: "true"/USE_REAL_LLM: "false"/' docker-compose.yml
            else
                # Linux
                sed -i 's/USE_REAL_LLM: "true"/USE_REAL_LLM: "false"/' docker-compose.yml
            fi
            print_success "Modo MOCK activado"
            ;;
        2)
            read -p "Ingresa tu API key de OpenAI: " OPENAI_KEY
            if [ -z "$OPENAI_KEY" ]; then
                print_error "API key vacía, usando modo MOCK"
                if [[ "$OSTYPE" == "darwin"* ]]; then
                    sed -i '' 's/USE_REAL_LLM: "true"/USE_REAL_LLM: "false"/' docker-compose.yml
                else
                    sed -i 's/USE_REAL_LLM: "true"/USE_REAL_LLM: "false"/' docker-compose.yml
                fi
            else
                # Reemplazar API key
                if [[ "$OSTYPE" == "darwin"* ]]; then
                    sed -i '' "s|OPENAI_API_KEY: \".*\"|OPENAI_API_KEY: \"$OPENAI_KEY\"|" docker-compose.yml
                    sed -i '' 's/USE_REAL_LLM: "false"/USE_REAL_LLM: "true"/' docker-compose.yml
                else
                    sed -i "s|OPENAI_API_KEY: \".*\"|OPENAI_API_KEY: \"$OPENAI_KEY\"|" docker-compose.yml
                    sed -i 's/USE_REAL_LLM: "false"/USE_REAL_LLM: "true"/' docker-compose.yml
                fi
                print_success "API key configurada"
            fi
            ;;
        3)
            print_info "Continuando con la configuración actual..."
            ;;
        *)
            print_warning "Opción no válida, usando configuración actual"
            ;;
    esac
else
    print_success "API key detectada en docker-compose.yml"
fi




# 4. LIMPIAR CONTENEDORES PREVIOS

print_header "LIMPIANDO CONTENEDORES PREVIOS"

# Preguntar si hacer limpieza completa
echo ""
read -p "¿Deseas hacer limpieza completa (eliminar volúmenes y datos)? (s/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[SsYy]$ ]]; then
    print_info "Deteniendo y eliminando contenedores y volúmenes..."
    $COMPOSE_CMD down -v 2>/dev/null || true
    print_success "Limpieza completa realizada"
else
    print_info "Deteniendo contenedores existentes..."
    $COMPOSE_CMD down 2>/dev/null || true
    print_success "Contenedores detenidos (volúmenes preservados)"
fi




# 5. CONSTRUIR IMÁGENES

print_header "CONSTRUYENDO IMÁGENES DOCKER"

print_info "Esto puede tomar varios minutos la primera vez..."
if $COMPOSE_CMD build --no-cache; then
    print_success "Imágenes construidas exitosamente"
else
    print_error "Error al construir imágenes"
    exit 1
fi





# 6. INICIAR SERVICIOS

print_header "INICIANDO SERVICIOS"

print_info "Iniciando infraestructura base (Kafka, PostgreSQL)..."
$COMPOSE_CMD up -d kafka postgres

print_info "Esperando a que Kafka esté listo (esto puede tomar 30-60 segundos)..."
sleep 10
MAX_WAIT=60
ELAPSED=0
while ! docker exec kafka /opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server kafka:9092 &>/dev/null; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        print_error "Kafka no respondió en $MAX_WAIT segundos"
        print_info "Revisa los logs con: $COMPOSE_CMD logs kafka"
        exit 1
    fi
    echo -n "."
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done
echo ""
print_success "Kafka está listo"

print_info "Esperando a que PostgreSQL esté listo..."
sleep 5
MAX_WAIT=30
ELAPSED=0
while ! docker exec postgres pg_isready -U user -d yahoo_answers_db &>/dev/null; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        print_error "PostgreSQL no respondió en $MAX_WAIT segundos"
        print_info "Revisa los logs con: $COMPOSE_CMD logs postgres"
        exit 1
    fi
    echo -n "."
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done
echo ""
print_success "PostgreSQL está listo"

print_info "Iniciando servicios de aplicación..."
$COMPOSE_CMD up -d storage_api llm_worker flink-jobmanager flink-taskmanager flink_job

print_info "Esperando a que Storage API esté listo..."
sleep 5
MAX_WAIT=30
ELAPSED=0
while ! curl -s http://localhost:8000/health &>/dev/null; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        print_warning "Storage API no respondió en $MAX_WAIT segundos (puede estar iniciando)"
        break
    fi
    echo -n "."
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done
echo ""
if curl -s http://localhost:8000/health | grep -q "ok"; then
    print_success "Storage API está listo"
else
    print_warning "Storage API puede estar iniciando todavía"
fi


echo ""
read -p "¿Deseas iniciar el generador de tráfico ahora? (s/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[SsYy]$ ]]; then
    print_info "Iniciando generador de tráfico..."
    $COMPOSE_CMD up -d traffic_gen
    print_success "Generador de tráfico iniciado"
else
    print_info "Puedes iniciarlo después con: $COMPOSE_CMD up -d traffic_gen"
fi




# 7. VERIFICAR ESTADO

print_header "VERIFICANDO ESTADO DE SERVICIOS"

# Esperar un poco para que los servicios se estabilicen
sleep 3

# Mostrar estado de contenedores
$COMPOSE_CMD ps



# 8. CREAR TOPICS DE KAFKA (si no existen)

print_header "VERIFICANDO TOPICS DE KAFKA"

print_info "Creando topics de Kafka si no existen..."

TOPICS=("preguntas" "llm_respuestas" "resultados_validados" "dlq" "preguntas.retry" "questions.new" "llm.requests")

for topic in "${TOPICS[@]}"; do
    if docker exec kafka /opt/kafka/bin/kafka-topics.sh \
        --bootstrap-server kafka:9092 \
        --list 2>/dev/null | grep -q "^$topic$"; then
        print_info "Topic '$topic' ya existe"
    else
        print_info "Creando topic '$topic'..."
        docker exec kafka /opt/kafka/bin/kafka-topics.sh \
            --bootstrap-server kafka:9092 \
            --create \
            --topic "$topic" \
            --partitions 3 \
            --replication-factor 1 2>/dev/null || print_warning "No se pudo crear '$topic' (puede autocrarse)"
    fi
done

print_success "Topics verificados"




# 9. MOSTRAR INFORMACIÓN ÚTIL

print_header "SISTEMA INICIADO EXITOSAMENTE"

print_info "URLs de acceso:"
echo "  • Storage API:     http://localhost:8000"
echo "  • Health Check:    http://localhost:8000/health"
echo "  • Flink UI:        http://localhost:8081"
echo "  • PostgreSQL:      localhost:5432 (user/password)"

echo ""
print_info "Comandos útiles:"
echo "  • Ver logs generales:       $COMPOSE_CMD logs -f"
echo "  • Ver logs de Flink Job:    $COMPOSE_CMD logs -f flink_job"
echo "  • Ver logs de LLM Worker:   $COMPOSE_CMD logs -f llm_worker"
echo "  • Ver logs de Traffic Gen:  $COMPOSE_CMD logs -f traffic_gen"
echo "  • Detener sistema:          $COMPOSE_CMD down"
echo "  • Ver estado:               $COMPOSE_CMD ps"

echo ""
print_info "Probar el sistema:"
echo '  curl -X POST http://localhost:8000/query \'
echo '    -H "Content-Type: application/json" \'
echo '    -d '"'"'{"question": "¿Qué es un árbol B+ en bases de datos?"}'"'"

echo ""
print_info "Monitorear PostgreSQL:"
echo "  docker exec -it postgres psql -U user -d yahoo_answers_db -c 'SELECT COUNT(*) FROM qa_results;'"

echo ""
print_info "Ver mensajes en DLQ:"
echo "  docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh \\"
echo "    --bootstrap-server kafka:9092 --topic dlq --from-beginning"

echo ""
print_success "¡El sistema está listo para usar!"
print_info "Revisa README.txt para más información"

echo ""
print_header "SETUP COMPLETO"
echo ""