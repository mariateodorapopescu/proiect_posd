FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
COPY src src
RUN mvn -B -ntp package

FROM eclipse-temurin:21-jre-alpine
RUN addgroup -S securesync && adduser -S securesync -G securesync \
    && mkdir -p /app/storage /data/pdfs && chown -R securesync:securesync /app /data/pdfs
WORKDIR /app
COPY --from=build /build/target/securesync-api-0.1.0.jar app.jar
USER securesync
EXPOSE 8081
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
