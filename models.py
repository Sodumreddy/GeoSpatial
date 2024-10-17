from flask_sqlalchemy import SQLAlchemy
from geoalchemy2 import Geometry
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

# Initialize the SQLAlchemy instance
db = SQLAlchemy()

class PointOfInterest(db.Model):
    __tablename__ = 'pois'

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    category = Column(String(255))
    location = Column(Geometry(geometry_type='POINT', srid=4326))  # PostGIS POINT type
    journey_id = Column(Integer, ForeignKey('journeys.id'))
    journey = relationship('Journey', back_populates='pois')

class Journey(db.Model):
    __tablename__ = 'journeys'

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(Geometry('POINT', srid=4326))
    destination = db.Column(Geometry('POINT', srid=4326))
    distance = db.Column(db.Float)  # Store the distance between source and destination
    created_at = db.Column(db.DateTime, default=db.func.now())
    pois = relationship('PointOfInterest', back_populates='journey')
