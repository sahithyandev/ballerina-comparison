plugins {
    application
    id("com.gradleup.shadow") version "9.1.0"
}

repositories {
    mavenCentral()
}

java {
    // Runs on the JDK Gradle itself is using (21+; developed on 26). No
    // toolchain auto-provisioning — one less moving part, same as the other
    // stacks using whatever's on PATH.
    sourceCompatibility = JavaVersion.VERSION_21
    targetCompatibility = JavaVersion.VERSION_21
}

application {
    mainClass = "blog.Main"
}

dependencies {
    implementation("io.javalin:javalin:6.7.0")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.19.2")
    implementation("jakarta.annotation:jakarta.annotation-api:3.0.0")
    implementation("org.xerial:sqlite-jdbc:3.50.3.0")
    implementation("com.auth0:java-jwt:4.5.0")
    implementation("at.favre.lib:bcrypt:0.10.2")
    implementation("ch.qos.logback:logback-classic:1.5.18")
    implementation("net.logstash.logback:logstash-logback-encoder:8.1")

    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

// Request DTOs under src/gen/java/blog/model are generated from
// ../openapi.yaml with the openapi-generator CLI and committed, the same
// separate-tool, commit-the-output convention as Go's oapi-codegen. Not a
// Gradle task (the gradle plugin isn't Gradle 9 compatible yet) — see
// scripts/gen-models.sh and CLAUDE.md for the regenerate command.

sourceSets {
    main {
        java {
            srcDir("src/gen/java")
        }
    }
}

tasks.test {
    useJUnitPlatform()
    testLogging { events("passed", "skipped", "failed") }
}

tasks.shadowJar {
    archiveBaseName = "blog-java"
    archiveClassifier = "all"
    archiveVersion = ""
    mergeServiceFiles()
}

tasks.build {
    dependsOn(tasks.shadowJar)
}
