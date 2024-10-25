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

@app.route('/generate_poi_story', methods=['POST'])
def generate_poi_story():
    try:
        data = request.get_json()
        poi_name = data.get('poi_name')
        poi_category = data.get('poi_category')

        if not poi_name or not poi_category:
            return jsonify({"error": "Missing POI information"}), 400

        # Create a story prompt based on the POI
        prompt = create_poi_story_prompt(poi_name, poi_category)
        
        # Generate story using Hugging Face API
        response = query_huggingface({"inputs": prompt})
        
        if response and isinstance(response, list) and 'generated_text' in response[0]:
            story = response[0]['generated_text']
            # Clean and format the story
            formatted_story = format_story(story)
            return jsonify({"story": formatted_story}), 200
        else:
            return jsonify({"error": "Failed to generate story"}), 500

    except Exception as e:
        print(f"Error generating POI story: {str(e)}")
        return jsonify({"error": str(e)}), 500
def create_poi_story_prompt(poi_name, poi_category):
    """Create an engaging prompt for the story generation based on POI type"""
    category_prompts = {
        'restaurant': f"Tell a short story about a memorable dining experience at {poi_name}, "
                     f"describing the atmosphere, signature dishes, and what makes it special.",
        'hotel': f"Describe a perfect stay at {poi_name}, highlighting its unique features "
                f"and what travelers might experience there.",
        'motel': f"Share an interesting traveler's tale about staying at {poi_name}, "
                f"focusing on its character and memorable aspects.",
        'park': f"Paint a picture of a beautiful day spent at {poi_name}, "
                f"describing its natural features and activities visitors can enjoy."
    }
    
    default_prompt = f"Tell an interesting story about visiting {poi_name}, "f"describing what makes this {poi_category} special and memorable."
    return category_prompts.get(poi_category.lower(), default_prompt)
def format_story(story):
    """
    Clean and format the generated story text
    
    Args:
        story (str): Raw story text from the API
        
    Returns:
        str: Formatted story with HTML paragraph tags
    """
    # Remove any extra whitespace and newlines
    story = ' '.join(story.split())
    
    # Add paragraph breaks for readability (every 3 sentences)
    sentences = story.split('. ')
    paragraphs = []
    current_paragraph = []
    
    for i, sentence in enumerate(sentences):
        current_paragraph.append(sentence)
        if (i + 1) % 3 == 0 or i == len(sentences) - 1:
            paragraphs.append('. '.join(current_paragraph) + '.')
            current_paragraph = []
    
    return '<p>' + '</p><p>'.join(paragraphs) + '</p>'
    
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