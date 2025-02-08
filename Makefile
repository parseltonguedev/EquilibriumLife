include .env
export

build-PythonDependenciesLayer:
	@mkdir -p "$(ARTIFACTS_DIR)/python"
	@python -m pip install -r requirements.txt --platform manylinux2014_x86_64 -t "$(ARTIFACTS_DIR)/python" --only-binary=:all:

build:
	sam build

deploy: build
	sam deploy \
		--no-confirm-changeset \
		--no-fail-on-empty-changeset \
		--parameter-overrides \
			TelegramToken=$(TELEGRAM_TOKEN) \
			OpenAIApiKey=$(OPENAI_API_KEY)

.PHONY: build deploy
