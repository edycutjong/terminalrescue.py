#!/bin/bash

# setup_foxmq.sh
# Downloads and configures FoxMQ v0.3.1 for a local 5-drone simulation

FOXMQ_VERSION="0.3.1"
ARCH=$(uname -m)
OS=$(uname -s | tr '[:upper:]' '[:lower:]')

# Determine correct URL based on OS/Arch
if [ "$OS" = "darwin" ]; then
    DOWNLOAD_URL="https://github.com/tashigit/foxmq/releases/download/v${FOXMQ_VERSION}/foxmq_${FOXMQ_VERSION}_macos-universal.zip"
    ZIP_NAME="foxmq_${FOXMQ_VERSION}_macos-universal.zip"
elif [ "$OS" = "linux" ]; then
    if [ "$ARCH" = "x86_64" ]; then
        DOWNLOAD_URL="https://github.com/tashigit/foxmq/releases/download/v${FOXMQ_VERSION}/foxmq_${FOXMQ_VERSION}_linux-x86_64.zip"
        ZIP_NAME="foxmq_${FOXMQ_VERSION}_linux-x86_64.zip"
    else
        echo "Linux architecture $ARCH not supported by this script natively yet."
        exit 1
    fi
else
    echo "OS $OS not supported by this script. Please download FoxMQ manually."
    exit 1
fi

echo "=== Downloading FoxMQ v${FOXMQ_VERSION} ==="
curl -LO $DOWNLOAD_URL

echo "=== Extracting FoxMQ ==="
unzip -o $ZIP_NAME
chmod +x foxmq
rm $ZIP_NAME

echo "=== Cleaning Up Old Configuration ==="
rm -rf foxmq.d/

echo "=== Generating FoxMQ Address Book ==="
./foxmq address-book from-range -f 127.0.0.1 19793 19793

echo "=== Creating Drone Users ==="
# User creation for drones
for i in {1..5}; do
    echo "Adding drone_$i..."
    ./foxmq user add "drone_$i" "demopass"
done
# User creation for observer
echo "Adding observer..."
./foxmq user add "observer" "demopass"

echo ""
echo "=== Setup Complete! ==="
echo "To start the FoxMQ broker, run: ./foxmq run --secret-key-file=foxmq.d/key_0.pem"
