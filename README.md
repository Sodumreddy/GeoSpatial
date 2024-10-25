 Project Documentation


Overview:
The "“Journey Narratives: Personalized Storytelling with Real-Time Travel
Recommendations”" project is a Flask-based web application that generates a personalized journey story between two locations, displays the journey on an interactive map, and highlights points of interest (POIs) along the route (like restaurants, motels, and parks). The application integrates Google Directions API for routing and Hugging Face API for story generation.

Features:
Users can input source and destination locations.
Generates a route between these locations using the Google Directions API.
Displays the journey route and calculates the distance between the two locations.
Shows nearby points of interest (POIs) on the route, including restaurants, motels, and parks.
Generates and displays a personalized journey story based on the user's preferences (mood, preferred stops) using the Hugging Face GPT-2 model.

Code Structure:
Backend (Flask):

app.py: The main Flask application that handles requests, interacts with external APIs, and manages the database.
Models: Journey and PointOfInterest models for storing journey and POI information in the database.
API Calls: Integration with Google Directions API for routes and Overpass API for POIs.
Story Generation: Integration with Hugging Face GPT-2 API to generate a journey story.


Frontend (HTML, JS, Leaflet.js):

index.html: The main page where users enter their locations and preferences.
app.js: JavaScript file that handles the map display, route drawing, POI display, and interaction with the backend.
Leaflet.js: Used to display the map, plot routes, and show POIs.
Leaflet Heatmap: Used to show a heatmap of POIs along the route.

Dependencies:
Flask: Backend framework for handling HTTP requests.
Leaflet.js: JavaScript library for interactive maps.
Google Directions API: For generating routes between two locations.
Overpass API: For fetching points of interest (POIs) along the route.
Hugging Face API: For generating personalized journey stories using GPT-2.

Instructions for Running the Project:
1. Clone the repository: git clone https://github.com/Sodumreddy/Geospatial-

2. Set up the environment:
Create a virtual environment and install the required packages:
python3 -m venv venv
source venv/bin/activate


3. Set up PostgreSQL database:
Ensure you have PostgreSQL installed, and create a new database for the project. Modify the SQLALCHEMY_DATABASE_URI in config.py with your PostgreSQL credentials.

4. Set up API keys:
In config.py, provide the following API keys:

HUGGINGFACE_API_KEY: API key for Hugging Face GPT-2.
GOOGLE_DIRECTIONS_API_KEY: API key for Google Directions API.

5. Running the Application:
Start the Flask application: flask run
The app will be running on http://127.0.0.1:5000/

