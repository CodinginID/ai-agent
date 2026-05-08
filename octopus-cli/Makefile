VERSION  := 0.2.0
APP_URL  ?= http://localhost:8080
LDFLAGS  := -ldflags="-X main.defaultAppURL=$(APP_URL) -X 'main.Version=$(VERSION)' -s -w"

.PHONY: build build-linux-amd64 build-linux-arm64 build-darwin-arm64 build-darwin-amd64 build-windows install clean release

build:
	go build $(LDFLAGS) -o bin/octopus .

build-linux-amd64:
	GOOS=linux GOARCH=amd64 go build $(LDFLAGS) -o bin/octopus-linux-amd64 .

build-linux-arm64:
	GOOS=linux GOARCH=arm64 go build $(LDFLAGS) -o bin/octopus-linux-arm64 .

build-darwin-arm64:
	GOOS=darwin GOARCH=arm64 go build $(LDFLAGS) -o bin/octopus-darwin-arm64 .

build-darwin-amd64:
	GOOS=darwin GOARCH=amd64 go build $(LDFLAGS) -o bin/octopus-darwin-amd64 .

build-windows:
	GOOS=windows GOARCH=amd64 go build $(LDFLAGS) -o bin/octopus-windows-amd64.exe .

install: build
	cp bin/octopus /usr/local/bin/octopus

clean:
	rm -rf bin/

release: build-linux-amd64 build-linux-arm64 build-darwin-arm64 build-darwin-amd64 build-windows
	@echo "Release binaries in bin/"
