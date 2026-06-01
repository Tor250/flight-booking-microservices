COMPOSE ?= docker compose

.PHONY: help up down restart build ps logs logs-booking logs-flight test test-static verify-all check sentinel auth clean

help:
	@echo "Доступные команды:"
	@echo "  make up            - поднять все сервисы"
	@echo "  make down          - остановить сервисы"
	@echo "  make restart       - перезапустить сервисы"
	@echo "  make build         - пересобрать образы"
	@echo "  make ps            - показать статус контейнеров"
	@echo "  make logs          - логи всех сервисов"
	@echo "  make logs-booking  - логи booking-service"
	@echo "  make logs-flight   - логи flight-service"
	@echo "  make test          - прогон test_requests.sh"
	@echo "  make test-static   - проверка нерантаймных требований"
	@echo "  make verify-all    - test + test-static"
	@echo "  make check         - детальная проверка по инструкции"
	@echo "  make sentinel      - проверить Redis Sentinel"
	@echo "  make auth          - подсказка по проверке UNAUTHENTICATED"
	@echo "  make clean         - остановить сервисы и удалить volume"

up:
	$(COMPOSE) up -d --build
	$(COMPOSE) ps

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart
	$(COMPOSE) ps

build:
	$(COMPOSE) build

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs --tail=200

logs-booking:
	$(COMPOSE) logs --tail=200 booking-service

logs-flight:
	$(COMPOSE) logs --tail=200 flight-service

test:
	bash test_requests.sh

test-static:
	bash check_static_requirements.sh

verify-all: test test-static

check:
	@echo "См. файл: удалить_перед_пушем/ИНСТРУКЦИЯ_ПРОВЕРКИ_ПО_ТРЕБОВАНИЯМ.md"

sentinel:
	$(COMPOSE) exec -T redis-sentinel-1 redis-cli -p 26379 sentinel ckquorum mymaster
	$(COMPOSE) exec -T redis-sentinel-1 redis-cli -p 26379 sentinel get-master-addr-by-name mymaster

auth:
	@echo "Проверка auth включена в make test (шаг 8/16)."

clean:
	$(COMPOSE) down -v --remove-orphans
