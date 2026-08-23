# Vizag Dashboard Mobile App

A React Native & Expo companion mobile application for the Vizag Traffic & Air Quality Intelligence Dashboard.

## Features

- **Live AQI & Weather**: Real-time air quality index monitoring across major Andhra Pradesh cities.
- **Traffic Congestion Index**: Congestion percentage and traffic status overview.
- **Next-Hour AQI Predictions**: Real-time forecast powered by ML models.
- **AI Root-Cause Insights**: Instant automated explanations and recommendations.
- **City Switcher**: Support for Visakhapatnam, Vijayawada, Guntur, Tirupati, Nellore, and Kurnool.
- **Pull-to-Refresh**: Instant live data synchronization with the backend API.

## Getting Started

### Prerequisites

- [Node.js](https://nodejs.org/) (v18+)
- [Expo Go app](https://expo.dev/go) installed on iOS or Android

### Installation

1. Install the Expo CLI globally (if not already installed):
   ```bash
   npm install -g expo-cli
   ```

2. Navigate to the `mobile/` directory:
   ```bash
   cd mobile
   ```

3. Install project dependencies:
   ```bash
   npm install
   ```

### Running the App

1. Ensure the FastAPI backend server is running on `http://localhost:8000`:
   ```bash
   # In the root project directory:
   uvicorn api.main:app --reload --port 8000
   ```
   *(Note: If running on a physical mobile device, update `API_BASE` in `App.js` with your computer's local network IP address, e.g., `http://192.168.1.x:8000`)*

2. Start the Expo development server:
   ```bash
   npx expo start
   ```

3. Open the app:
   - **Android / iOS Physical Device**: Scan the QR code shown in the terminal using the Expo Go app (or Camera app on iOS).
   - **Android Emulator**: Press `a` in the terminal.
   - **iOS Simulator**: Press `i` in the terminal.
   - **Web Browser**: Press `w` in the terminal.
