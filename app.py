from flask import Flask, request, jsonify, render_template
import requests
from config import Config
from models import Journey, PointOfInterest, db
from geoalchemy2 import WKTElement
from flask_cors import CORS
import os

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
CORS(app)

# Hugging Face API URL and Key
HF_API_URL = "https://api-inference.huggingface.co/models/gpt2"
HF_HEADERS = {"Authorization": f"Bearer {app.config['HUGGINGFACE_API_KEY']}"}
GOOGLE_DIRECTIONS_API_KEY = 'AIzaSyA6-4YefziDQSdQJK12AIg4za7RmcQ0ago'

# Directions API endpoint
GOOGLE_DIRECTIONS_API_URL = "https://maps.googleapis.com/maps/api/directions/json"


def query_huggingface(payload):
    response = requests.post(HF_API_URL, headers=HF_HEADERS, json=payload)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch story: {response.status_code}, {response.text}")
        return None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/save_journey', methods=['POST'])
def save_journey():
    data = request.get_json()

    source_lat = data['source']['lat']
    source_lon = data['source']['lon']
    dest_lat = data['destination']['lat']
    dest_lon = data['destination']['lon']

    source_geom = WKTElement(f'POINT({source_lon} {source_lat})', srid=4326)
    destination_geom = WKTElement(f'POINT({dest_lon} {dest_lat})', srid=4326)

    # Google Directions API call
    directions_api_url = (
        f"https://maps.googleapis.com/maps/api/directions/json?"
        f"origin={source_lat},{source_lon}&destination={dest_lat},{dest_lon}"
        f"&alternatives=true&key={GOOGLE_DIRECTIONS_API_KEY}"
    )
    response = requests.get(directions_api_url)
    directions_data = response.json()

    if directions_data.get('status') == 'OK':
        distance_text = directions_data['routes'][0]['legs'][0]['distance']['text']
        distance_value = directions_data['routes'][0]['legs'][0]['distance']['value'] / 1000.0

        journey = Journey(source=source_geom, destination=destination_geom, distance=distance_value)
        db.session.add(journey)
        db.session.commit()

        return jsonify({"message": "Journey saved successfully!", "distance": distance_text, "routes": directions_data['routes']}), 201
    else:
        return jsonify({"error": "Failed to calculate route"}), 400


def fetch_pois_from_overpass(source_lat, source_lon, dest_lat, dest_lon, proximity_km=10):
    try:
        # Proximity limit to filter POIs within a certain distance (in kilometers)
        proximity_limit = proximity_km / 111  # Convert km to degrees (approx for lat/lon)

        # Define a bounding box that limits the search area to a range around the route
        min_lat = min(source_lat, dest_lat) - proximity_limit
        max_lat = max(source_lat, dest_lat) + proximity_limit
        min_lon = min(source_lon, dest_lon) - proximity_limit
        max_lon = max(source_lon, dest_lon) + proximity_limit

        # Overpass query to fetch POIs within the limited area
        overpass_query = f"""
        [out:json][timeout:25];
        (
          nwr["tourism"="hotel"]({min_lat},{min_lon},{max_lat},{max_lon});
          nwr["tourism"="motel"]({min_lat},{min_lon},{max_lat},{max_lon});
          nwr["leisure"="park"]({min_lat},{min_lon},{max_lat},{max_lon});
          nwr["amenity"="restaurant"]({min_lat},{min_lon},{max_lat},{max_lon});
        );
        out geom;
        """
        response = requests.post('https://overpass-api.de/api/interpreter', data={'data': overpass_query})
        response.raise_for_status()
        return response.json().get('elements', [])
    except requests.exceptions.RequestException as e:
        print(f"Error fetching POIs from Overpass API: {e}")
        return []




@app.route('/fetch_pois', methods=['POST'])
def fetch_pois():
    try:
        data = request.get_json()
        source_coords = data['source']
        destination_coords = data['destination']
        proximity_km = data.get('proximity_km', 10)  # Default to 10 km proximity

        # Fetch POIs using dynamic bounding box based on source, destination, and proximity
        pois = fetch_pois_from_overpass(source_coords['lat'], source_coords['lon'], destination_coords['lat'], destination_coords['lon'], proximity_km)

        poi_list = []
        for poi in pois:
            if 'lat' in poi and 'lon' in poi:
                name = poi['tags'].get('name', 'Unknown POI')
                category = poi['tags'].get('tourism') or poi['tags'].get('leisure') or poi['tags'].get('amenity') or 'unknown'
                lat = poi['lat']
                lon = poi['lon']
                poi_list.append({
                    "name": name,
                    "category": category,
                    "location": {"lat": lat, "lon": lon}
                })

        if poi_list:
            return jsonify({"pois": poi_list}), 200
        else:
            return jsonify({"error": "No POIs found"}), 400
    except Exception as e:
        print("Error in /fetch_pois:", str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/generate_story', methods=['POST'])
def generate_story():
    try:
        data = request.get_json()
        print("Received data for story generation:", data)

        location1_name = data.get('location1')
        location2_name = data.get('location2')
        mood = data.get('mood', 'adventurous')
        preferred_stops = data.get('preferred_stops', ['restaurants', 'motels', 'parks'])

        if not location1_name or not location2_name:
            return jsonify({"error": "Location1 or Location2 is missing"}), 400

        # Fetch POIs from Overpass API (you might want to check if this function is working correctly)
        pois = fetch_pois_from_overpass()
        if not pois:
            return jsonify({"error": "No points of interest found"}), 400

        poi_names = [poi['tags'].get('name', 'Unknown POI') for poi in pois]
        poi_list = ", ".join(poi_names)

        # Creating the story prompt
        prompt = (f"Create a personalized journey story for a {mood} trip from {location1_name} to {location2_name}. "
                  f"The traveler prefers to stop at places like {', '.join(preferred_stops)}. "
                  f"Along the way, they will encounter stops like {poi_list}. "
                  f"Describe the journey in an exciting way, focusing on these stops and the beauty of the route.")

        print("Sending prompt to Hugging Face API:", prompt)

        # Sending the story generation request to Hugging Face
        response = query_huggingface({"inputs": prompt})
        print("Hugging Face API response:", response)

        if response and isinstance(response, list) and 'generated_text' in response[0]:
            story = response[0]['generated_text']
            return jsonify({"story": story, "pois": poi_names})
        else:
            return jsonify({"error": "Failed to generate story from API response"}), 500

    except Exception as e:
        print(f"Error in generating story: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/fetch_routes', methods=['POST'])
def fetch_routes():
    try:
        data = request.get_json()

        source_lat = data['source']['lat']
        source_lon = data['source']['lon']
        dest_lat = data['destination']['lat']
        dest_lon = data['destination']['lon']

        if not all([source_lat, source_lon, dest_lat, dest_lon]):
            return jsonify({"error": "Missing source or destination coordinates"}), 400

        # Google Directions API URL with proper parameters
        directions_api_url = (
            f"https://maps.googleapis.com/maps/api/directions/json?"
            f"origin={source_lat},{source_lon}&destination={dest_lat},{dest_lon}"
            f"&alternatives=true&key={GOOGLE_DIRECTIONS_API_KEY}"
        )

        print(f"Fetching directions from {source_lat},{source_lon} to {dest_lat},{dest_lon}")
        response = requests.get(directions_api_url)
        
        # Check if request was successful
        if response.status_code != 200:
            print(f"Google API response error: {response.status_code} {response.text}")
            return jsonify({"error": "Failed to fetch directions from Google"}), 400

        directions_data = response.json()

        if directions_data.get('status') == 'OK':
            return jsonify(directions_data), 200
        else:
            return jsonify({"error": "Failed to calculate route: " + directions_data.get('status')}), 400
    except Exception as e:
        print(f"Error in /fetch_routes: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/get_journeys', methods=['GET'])
def get_journeys():
    try:
        journeys = Journey.query.all()
        journeys_data = []
        for journey in journeys:
            journeys_data.append({
                "source": {
                    "lat": db.session.scalar(journey.source.ST_Y()),
                    "lon": db.session.scalar(journey.source.ST_X())
                },
                "destination": {
                    "lat": db.session.scalar(journey.destination.ST_Y()),
                    "lon": db.session.scalar(journey.destination.ST_X())
                },
                "distance": journey.distance
            })

        return jsonify(journeys_data), 200
    except Exception as e:
        print("Error in /get_journeys:", str(e))
        return jsonify({"error": str(e)}), 500

def store_pois_in_db(pois, journey_id):
    for poi in pois:
        if 'lat' in poi and 'lon' in poi:
            name = poi['tags'].get('name', 'Unknown POI')
            category = poi['tags'].get('tourism') or poi['tags'].get('leisure') or poi['tags'].get('amenity') or 'unknown'
            lat = poi['lat']
            lon = poi['lon']
            
            # Create a new PointOfInterest record
            poi_record = PointOfInterest(
                name=name,
                category=category,
                location=WKTElement(f'POINT({lon} {lat})', srid=4326),  # Storing as PostGIS POINT
                journey_id=journey_id
            )
            db.session.add(poi_record)
    
    db.session.commit()
@app.route('/get_heatmap_data', methods=['GET'])
def get_heatmap_data():
    journey_id = request.args.get('journey_id')  # Assuming you pass journey_id as a parameter
    pois = PointOfInterest.query.filter_by(journey_id=journey_id).all()
    
    poi_list = []
    for poi in pois:
        poi_list.append({
            'name': poi.name,
            'category': poi.category,
            'location': {
                'lat': db.session.scalar(poi.location.ST_Y()),  # Extract latitude
                'lon': db.session.scalar(poi.location.ST_X())   # Extract longitude
            }
        })

    return jsonify({'pois': poi_list}), 200

if __name__ == '__main__':
    app.run(debug=True)
