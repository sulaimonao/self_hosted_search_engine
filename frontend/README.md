# Frontend

This directory contains the Next.js frontend for the self-hosted search engine.

## Development

To run the frontend in development mode, you'll need to have Node.js and npm installed.

### Setup

1.  **Install dependencies:**
    From the root of the repository, run the following command to install both backend and frontend dependencies:
    ```bash
    make setup
    ```

2.  **Run the development server:**
    From the root of the repository, run the following command to start both the backend and frontend development servers:
    ```bash
    make dev
    ```
    The frontend will be available at [http://localhost:3000](http://localhost:3000).

### Manual Setup

If you prefer to run the frontend separately, you can use the following commands from within the `frontend` directory:

1.  **Install dependencies:**
    ```bash
    npm install
    ```

2.  **Run the development server:**
    ```bash
    npm run dev
    ```