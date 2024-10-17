// Initialize the map centered in Minnesota
const map = L.map('map').setView([46.7296, -94.6859], 7);

// Add tile layer from OpenStreetMap
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors'
}).addTo(map);

// Heatmap layer
let heatmapLayer;

// Function to fetch coordinates from Nominatim API
async function getCoordinates(location) {
    const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(location)}&format=json&limit=1`;
    const response = await fetch(url);
    const data = await response.json();

    if (data && data.length > 0) {
        return { name: location, lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon) };
    } else {
        throw new Error("Location not found");
    }
}

// Handle form submission for source, destination, and user preferences
document.getElementById('locationForm').addEventListener('submit', async function (event) {
    event.preventDefault();

    const source = document.getElementById('source').value;
    const destination = document.getElementById('destination').value;
    const mood = document.getElementById('mood').value;

    const preferredStops = [];
    if (document.getElementById('restaurants').checked) preferredStops.push('restaurants');
    if (document.getElementById('motels').checked) preferredStops.push('motels');
    if (document.getElementById('parks').checked) preferredStops.push('parks');

    try {
        const sourceCoords = await getCoordinates(source);
        const destinationCoords = await getCoordinates(destination);

        console.log("Source coordinates:", sourceCoords);
        console.log("Destination coordinates:", destinationCoords);

        const payload = {
            source: sourceCoords,
            destination: destinationCoords,
            mood: mood,
            preferred_stops: preferredStops
        };

        console.log("Sending payload to /fetch_routes:", payload);
        await fetchRoutes(payload);
    } catch (error) {
        console.error("Error in form submission:", error);
    }
});

async function fetchRoutes(payload) {
    try {
        const response = await fetch('/fetch_routes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error(`Failed to fetch routes: ${response.statusText}`);
        }

        const data = await response.json();
        if (data.routes) {
            console.log("Routes data:", data);

            // Fetch and display POIs
            await fetchAndDisplayHeatMap(payload.source, payload.destination);
            await generateStory(payload);
        } else {
            console.error("Error fetching routes:", data.error);
        }
    } catch (error) {
        console.error("Error:", error);
    }
}

async function fetchAndDisplayHeatMap(sourceCoords, destinationCoords) {
    try {
        const response = await fetch('/fetch_pois', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                source: sourceCoords,
                destination: destinationCoords,
                proximity_km: 10  // Limit search area to within 10 kilometers of the route
            })
        });

        if (!response.ok) {
            throw new Error(`Failed to fetch POIs: ${response.statusText}`);
        }

        const data = await response.json();
        if (data.pois && data.pois.length > 0) {
            const heatPoints = data.pois.map(poi => [poi.location.lat, poi.location.lon]);

            // Clear existing heatmap layer and markers if they exist
            if (heatmapLayer) {
                map.removeLayer(heatmapLayer);
            }

            heatmapLayer = L.heatLayer(heatPoints, { radius: 25 }).addTo(map);

            data.pois.forEach(poi => {
                L.marker([poi.location.lat, poi.location.lon])
                    .addTo(map)
                    .bindPopup(`${poi.name} (${poi.category})`);
            });
        } else {
            console.error('No POIs found');
        }
    } catch (error) {
        console.error('Error fetching POIs:', error);
    }
}



async function generateStory(payload) {
    try {
        const response = await fetch('/generate_story', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error(`Failed to generate story: ${response.statusText}`);
        }

        const data = await response.json();
        if (data && data.story) {
            document.getElementById('story').innerText = data.story;
        } else {
            console.error('Error generating story:', data.error);
        }
    } catch (error) {
        console.error("Error generating story:", error);
        document.getElementById('story').innerText = "An error occurred while generating the story.";
    }
}
