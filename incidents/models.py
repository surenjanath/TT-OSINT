from django.db import models
from articles.models import Article


class Incident(models.Model):
    """An incident extracted from a news article by the AI engine."""

    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    CATEGORY_CHOICES = [
        ('violent_crime', 'Violent Crime'),
        ('robbery', 'Robbery'),
        ('assault', 'Assault'),
        ('shooting', 'Shooting'),
        ('murder', 'Murder'),
        ('kidnapping', 'Kidnapping'),
        ('traffic_accident', 'Traffic Accident'),
        ('vehicle_collision', 'Vehicle Collision'),
        ('pedestrian_accident', 'Pedestrian Accident'),
        ('fire', 'Fire'),
        ('flood', 'Flood'),
        ('natural_disaster', 'Natural Disaster'),
        ('police_activity', 'Police Activity'),
        ('drug_related', 'Drug Related'),
        ('domestic_violence', 'Domestic Violence'),
        ('fraud', 'Fraud'),
        ('other', 'Other'),
    ]

    REGION_CHOICES = [
        ('port_of_spain', 'Port of Spain'),
        ('san_fernando', 'San Fernando'),
        ('chaguanas', 'Chaguanas'),
        ('arima', 'Arima'),
        ('point_fortin', 'Point Fortin'),
        ('diego_martin', 'Diego Martin'),
        ('tunapuna_piarco', 'Tunapuna-Piarco'),
        ('san_juan_laventille', 'San Juan-Laventille'),
        ('couva_tabaquite_talparo', 'Couva-Tabaquite-Talparo'),
        ('sangre_grande', 'Sangre Grande'),
        ('siparia', 'Siparia'),
        ('penal_debe', 'Penal-Debe'),
        ('princes_town', 'Princes Town'),
        ('mayaro_rio_claro', 'Mayaro-Rio Claro'),
        ('tobago', 'Tobago'),
        ('unknown', 'Unknown'),
    ]

    # Core fields
    incident_type = models.CharField(max_length=100)
    category = models.CharField(
        max_length=50, choices=CATEGORY_CHOICES, default='other'
    )
    description = models.TextField()
    severity = models.CharField(
        max_length=20, choices=SEVERITY_CHOICES, default='medium'
    )

    # Location fields
    location_name = models.CharField(max_length=300, blank=True, default='')
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    region = models.CharField(
        max_length=50, choices=REGION_CHOICES, default='unknown'
    )

    # Enriched detail fields (extracted by AI)
    victim_count = models.IntegerField(default=0, help_text="Number of victims (injured + killed)")
    fatality_count = models.IntegerField(default=0, help_text="Number of fatalities")
    injured_count = models.IntegerField(default=0, help_text="Number injured (excluding fatalities)")
    value_stolen = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Estimated monetary value stolen (e.g. theft/robbery/fraud)"
    )
    premises_type = models.CharField(
        max_length=50, blank=True, default='',
        help_text="e.g. residence, business, road, school"
    )
    motive = models.CharField(max_length=100, blank=True, default='')
    is_resolved = models.BooleanField(
        default=False,
        help_text="True if arrests made or case resolved"
    )
    weapon = models.CharField(max_length=100, blank=True, default='', help_text="Weapon used")
    suspect_description = models.CharField(max_length=500, blank=True, default='')
    vehicle_info = models.CharField(max_length=300, blank=True, default='')
    incident_time = models.CharField(max_length=10, blank=True, default='', help_text="HH:MM 24h format")

    # AI-specific location detail (raw text from AI before geocoding)
    ai_location_raw = models.CharField(max_length=500, blank=True, default='',
        help_text="Raw location string as extracted by AI")
    ai_city = models.CharField(max_length=200, blank=True, default='')

    # Metadata
    incident_date = models.DateTimeField(blank=True, null=True,
        help_text="Always set to article published_date for reliability")
    ai_incident_date = models.DateTimeField(blank=True, null=True,
        help_text="Date extracted by AI (may be inaccurate, kept for analysis)")
    confidence_score = models.FloatField(
        default=0.0,
        help_text="AI extraction confidence (0-100)"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )

    # Relations
    primary_article = models.ForeignKey(
        Article, on_delete=models.CASCADE, related_name='incidents',
        blank=True, null=True,
        help_text="First article that created this incident"
    )
    related_articles = models.ManyToManyField(
        Article, related_name='linked_incidents', blank=True,
        help_text="All articles reporting this incident (including primary)"
    )
    is_duplicate = models.BooleanField(
        default=False,
        help_text="True if this incident was merged from a duplicate"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-incident_date', '-created_at']

    def __str__(self):
        return f"{self.incident_type} — {self.location_name or 'Unknown location'}"

    @property
    def severity_color(self):
        """Return CSS color class for severity level."""
        return {
            'low': '#3b82f6',
            'medium': '#f59e0b',
            'high': '#f97316',
            'critical': '#ef4444',
        }.get(self.severity, '#6b7280')

    @property
    def category_color(self):
        """Return marker color for map display."""
        color_map = {
            'violent_crime': '#ef4444',
            'shooting': '#dc2626',
            'murder': '#991b1b',
            'robbery': '#f97316',
            'assault': '#ea580c',
            'kidnapping': '#b91c1c',
            'traffic_accident': '#eab308',
            'vehicle_collision': '#ca8a04',
            'pedestrian_accident': '#a16207',
            'fire': '#3b82f6',
            'flood': '#6366f1',
            'natural_disaster': '#8b5cf6',
            'police_activity': '#06b6d4',
            'drug_related': '#d946ef',
            'domestic_violence': '#e11d48',
            'fraud': '#14b8a6',
        }
        return color_map.get(self.category, '#6b7280')

    def to_geojson_feature(self):
        """Return this incident as a GeoJSON Feature dict."""
        if not self.latitude or not self.longitude:
            return None
        return {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [self.longitude, self.latitude],
            },
            'properties': {
                'id': self.id,
                'incident_type': self.incident_type,
                'category': self.category,
                'category_display': self.get_category_display(),
                'description': self.description[:200],
                'location_name': self.location_name,
                'region': self.region,
                'region_display': self.get_region_display(),
                'severity': self.severity,
                'severity_color': self.severity_color,
                'category_color': self.category_color,
                'confidence_score': self.confidence_score,
                'incident_date': self.incident_date.isoformat() if self.incident_date else '',
                'incident_time': self.incident_time or '',
                'victim_count': self.victim_count,
                'fatality_count': self.fatality_count,
                'weapon': self.weapon,
                'suspect_description': self.suspect_description,
                'vehicle_info': self.vehicle_info,
                'source_url': self.primary_article.url if self.primary_article else '',
                'source_name': self.primary_article.source.name if self.primary_article and self.primary_article.source else '',
                'image_url': self.primary_article.image_url if self.primary_article else '',
                'article_id': self.primary_article.pk if self.primary_article else None,
                'ai_incident_date': self.ai_incident_date.isoformat() if self.ai_incident_date else '',
                'ai_city': self.ai_city,
            },
        }

    def get_source_articles(self):
        """Return all articles linked to this incident: primary first, then related_articles (excluding primary)."""
        articles = []
        if self.primary_article_id:
            articles.append(self.primary_article)
        for a in self.related_articles.exclude(pk=self.primary_article_id):
            articles.append(a)
        return articles


class Person(models.Model):
    """A victim, suspect, witness, or arrested person linked to an incident."""

    ROLE_CHOICES = [
        ('victim', 'Victim'),
        ('suspect', 'Suspect'),
        ('witness', 'Witness'),
        ('arrested', 'Arrested'),
    ]
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('unknown', 'Unknown'),
    ]
    CONDITION_CHOICES = [
        ('uninjured', 'Uninjured'),
        ('injured', 'Injured'),
        ('hospitalized', 'Hospitalized'),
        ('deceased', 'Deceased'),
        ('unknown', 'Unknown'),
    ]

    incident = models.ForeignKey(
        Incident, on_delete=models.CASCADE, related_name='persons'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    name = models.CharField(max_length=300, blank=True, default='')
    age = models.IntegerField(null=True, blank=True)
    gender = models.CharField(
        max_length=10, choices=GENDER_CHOICES, default='unknown'
    )
    condition = models.CharField(
        max_length=20, choices=CONDITION_CHOICES, default='unknown'
    )
    description = models.TextField(blank=True, default='')
    address = models.CharField(max_length=500, blank=True, default='')
    occupation = models.CharField(max_length=200, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['role', 'name']

    def __str__(self):
        return f"{self.get_role_display()}: {self.name or 'Unknown'}"
