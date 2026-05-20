.PHONY: up down logs reset ps

# Docker Compose 项目目录
COMPOSE_DIR := deploy
COMPOSE_FILE := $(COMPOSE_DIR)/docker-compose.yml
COMPOSE_DEV := $(COMPOSE_DIR)/docker-compose.dev.yml
COMPOSE := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_DEV) --project-name agentic-mlops

# --- 基础设施 ---

up: ## 启动所有服务
	$(COMPOSE) up -d
	@echo "Waiting for services to be healthy..."
	@scripts/wait-for-services.sh

down: ## 停止所有服务
	$(COMPOSE) down

logs: ## 查看服务日志（可选 s=服务名）
	$(COMPOSE) logs -f $(s)

ps: ## 查看服务状态
	$(COMPOSE) ps

reset: ## 重置所有数据（删除 volumes）
	$(COMPOSE) down -v
	@echo "All volumes removed."

# --- 开发 ---

lint: ## 运行 linter
	ruff check .
	mypy packages/

fmt: ## 格式化代码
	ruff format .

test: ## 运行测试
	pytest

test-cov: ## 运行测试（带覆盖率）
	pytest --cov=packages --cov-report=term-missing --cov-fail-under=70

# --- 帮助 ---

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
