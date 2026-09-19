#!/usr/bin/env bash
# Regenerate java/src/gen/java/blog/model/*.java from the shared openapi.yaml.
# Run this whenever openapi.yaml changes, then commit the result — same
# separate-tool, commit-the-output convention as Go's oapi-codegen. Needs
# `openapi-generator` on PATH (brew install openapi-generator).
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf java/src/gen
openapi-generator generate \
  -i openapi.yaml \
  -g jaxrs-spec \
  -o java/src/gen \
  --global-property models,modelDocs=false,modelTests=false \
  --model-package blog.model \
  --additional-properties=sourceFolder=java,useJakartaEe=true,useBeanValidation=false,useSwaggerAnnotations=false,generatePom=false,hideGenerationTimestamp=true,openApiNullable=false,returnResponse=false

# Keep only the generator's model sources, drop its project scaffold, and
# within that keep only the request DTOs the handlers actually bind (App.java).
# Responses are built as plain maps, same as rust/src/app.rs's json! bodies.
find java/src/gen -mindepth 1 -maxdepth 1 ! -name java -exec rm -rf {} +
find java/src/gen/java -mindepth 1 -maxdepth 1 ! -name blog -exec rm -rf {} +
cd java/src/gen/java/blog/model
for f in *.java; do
  case "$f" in
    RegisterRequest.java|LoginRequest.java|CreatePostRequest.java|UpdatePostRequest.java|CreateCommentRequest.java) ;;
    *) rm "$f" ;;
  esac
done
echo "generated:"
ls
