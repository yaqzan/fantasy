# NBA Fantasy Frontend

React application for NBA fantasy basketball player statistics and draft management.

## Quick Start

1. Install dependencies:
   ```bash
   npm install
   ```

2. Start the development server:
   ```bash
   npm start
   ```

The application will be available at `http://localhost:3000`

## Features

- **Sortable Player Table**: Click column headers to sort by any statistic
- **Search Functionality**: Search players by name or team
- **Draft System**: Draft players to fantasy teams with modal selection
- **Filter Toggle**: Show available players only or all players
- **Responsive Design**: Works on desktop and mobile devices
- **Modern UI**: NBA-themed dark interface with smooth animations

## Key Components

- `App.js` - Main application component with state management
- `PlayerTable.js` - Sortable table displaying player statistics
- `TeamManager.js` - Fantasy team creation and management
- `DraftModal.js` - Modal for drafting players to teams
- `Header.js` - Application header with branding

## Styling

- **Tailwind CSS** for utility-first styling
- **Custom NBA Theme** with team colors
- **Dark Mode** by default for better viewing experience
- **Responsive Grid** layouts for different screen sizes

## API Integration

The frontend communicates with the Flask backend through:
- `services/api.js` - Axios-based API client
- Automatic proxy configuration for development
- Error handling and loading states

## Development

- Built with React 18 and functional components
- Uses React hooks for state management
- Hot reloading enabled in development mode
- ESLint configuration included
