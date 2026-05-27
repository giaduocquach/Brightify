.PHONY: init dev dev-detach staging prod migrate seed warmup shell dbshell logs logs-app backup backup-snapshot restore-db clean clean-all reset-db verify

init: ## Create var/ structure + secrets on first setup
	@mkdir -p var/runtime/{music_files,album_art,artist_images,checkpoints,processed,essentia_models,annotations,trained_models}
	@mkdir -p var/runtime/backtest/{ground_truth,test_sets,baselines,reports,ci_artifacts}
	@mkdir -p var/volumes/{postgres_data,redis_data,hf_cache}
	@mkdir -p var/secrets var/backups/{db,snapshots,models} var/logs/{app,nginx,postgres}
	@mkdir -p logs/app logs/nginx  # default LOGS_PATH=./logs used by docker-compose
	@chmod 700 var/secrets
	@if [ ! -f var/secrets/db_password.txt ]; then \
		openssl rand -hex 32 > var/secrets/db_password.txt; \
		openssl rand -hex 32 > var/secrets/admin_key.txt; \
		openssl rand -hex 32 > var/secrets/redis_password.txt; \
		chmod 600 var/secrets/*.txt; \
		echo "Generated secrets in var/secrets/"; \
	fi
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example — review and fill in values!"; \
	fi
	@echo "Brightify directory structure ready"

setup: ## First-time full setup (init + db + migrate + seed + warmup + start)
	bash scripts/initial-setup.sh

dev: init ## Start dev stack with hot reload (foreground)
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

dev-detach: init ## Start dev stack detached
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

staging: init ## Start staging stack
	docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d

prod: init ## Start production stack
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

migrate: ## Apply Alembic migrations inside running stack
	docker compose run --rm migrate

seed: ## Seed DB from processed CSV
	docker compose run --rm app python -m db.seed

warmup: ## Pre-download HuggingFace models into hf_cache volume
	docker compose run --rm app python -c "\
from transformers import AutoTokenizer, AutoModel, CLIPModel, CLIPProcessor; \
AutoTokenizer.from_pretrained('vinai/phobert-base-v2'); \
AutoModel.from_pretrained('vinai/phobert-base-v2'); \
CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32'); \
CLIPModel.from_pretrained('openai/clip-vit-base-patch32'); \
print('Models cached')"

shell: ## Open bash shell in app container
	docker compose exec app /bin/bash

dbshell: ## Open psql shell in db container
	docker compose exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}

logs: ## Tail all service logs
	docker compose logs -f --tail=100

logs-app: ## Tail app logs only
	docker compose logs -f app

backup: ## Manual DB backup
	bash scripts/backup-db.sh

backup-snapshot: ## Manual runtime snapshot
	bash scripts/backup-snapshot.sh

restore-db: ## Restore latest DB dump (prompts for confirmation)
	@echo "WARNING: This will REPLACE current DB. Latest backup:"
	@ls -t var/backups/db/*.sql.gz | head -1
	@read -p "Continue? (yes/no) " ANS && [ "$$ANS" = "yes" ] || exit 1
	gunzip -c $$(ls -t var/backups/db/*.sql.gz | head -1) | \
		docker compose exec -T db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}

clean: ## Stop containers (keeps volumes and data)
	docker compose down
	@echo "Containers down. Data preserved in var/volumes/"

clean-all: ## DANGER: stop containers AND delete named volumes
	@echo "WARNING: This will DELETE postgres_data + redis_data + hf_cache!"
	@read -p "Type 'DELETE' to confirm: " ANS && [ "$$ANS" = "DELETE" ] || exit 1
	docker compose down -v
	rm -rf var/volumes/* var/logs/*

reset-db: backup ## Backup current DB then reset from seed
	docker compose stop app db
	rm -rf var/volumes/postgres_data/*
	docker compose up -d db
	@sleep 10
	$(MAKE) migrate seed
	docker compose start app

verify: ## Health-check all services
	@docker compose ps
	@curl -fsS http://localhost:8000/api/health | python -m json.tool || echo "App unhealthy"
