
ifneq ($(shell which docker-compose 2>/dev/null),)
    DOCKER_COMPOSE := docker-compose
else
    DOCKER_COMPOSE := docker compose
endif

install:
	$(DOCKER_COMPOSE) up -d

remove:
	@chmod +x confirm_remove.sh
	@./confirm_remove.sh

start:
	$(DOCKER_COMPOSE) start
startAndBuild: 
	$(DOCKER_COMPOSE) up -d --build

stop:
	$(DOCKER_COMPOSE) stop

update:
	# Calls the LLM update script
	chmod +x update_ollama_models.sh
	@./update_ollama_models.sh
	@git pull
	$(DOCKER_COMPOSE) down
	# Make sure the ollama-webui container is stopped before rebuilding
	@docker stop open-webui || true
	$(DOCKER_COMPOSE) up --build -d
	$(DOCKER_COMPOSE) start

# ──────────────────────────────────────────────
# GCP / Terraform
# ──────────────────────────────────────────────

GCP_PROJECT  ?= $(shell gcloud config get-value project 2>/dev/null)
GCP_REGION   ?= us-central1
REGISTRY     ?= $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/rome-registry
IMAGE        ?= $(REGISTRY)/open-webui
TAG          ?= latest
TF_DIR       := terraform

# --- Docker build & push ---

gcp-auth:
	gcloud auth configure-docker $(GCP_REGION)-docker.pkg.dev --quiet

gcp-build:
	docker build --platform linux/amd64 --build-arg USE_SLIM=true -t $(IMAGE):$(TAG) .

gcp-push: gcp-auth
	docker push $(IMAGE):$(TAG)

gcp-build-push: gcp-build gcp-push

# Cloud Build (build in GCP, no local Docker needed)
gcp-cloud-build:
	gcloud builds submit --region=$(GCP_REGION) --machine-type=e2-highcpu-8 --timeout=1800 --config=cloudbuild.yaml .

# --- Terraform ---

tf-init:
	cd $(TF_DIR) && terraform init

tf-plan:
	cd $(TF_DIR) && terraform plan

tf-apply:
	cd $(TF_DIR) && terraform apply

tf-destroy:
	cd $(TF_DIR) && terraform destroy

tf-output:
	cd $(TF_DIR) && terraform output

# --- Cloud Run deploy (redeploy with latest image, no TF needed) ---

gcp-deploy:
	gcloud run services update rome-openwebui \
		--region $(GCP_REGION) \
		--image $(IMAGE):$(TAG)

# --- Full pipeline: build, push, deploy ---

gcp-release: gcp-build-push gcp-deploy

