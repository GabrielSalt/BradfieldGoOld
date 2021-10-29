import itertools
import math
import random
import os
import smtplib, ssl

import simplekml
from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from fastkml import kml
from PIL import Image, ImageDraw

from .models import User

def GetPosition(coordinates):
    dimensions = [1164,1988]
    pos = []
    bottom, top, left, right = 51.444687, 51.452396, -1.142394, -1.121153
    pos.append((coordinates[0]-left)/(right-left)*dimensions[1])
    pos.append((top-coordinates[1])/(top-bottom)*dimensions[0])
    return pos

def GetDistance(coordinates):
    length = 0
    height = 0
    for x in range(len(coordinates)-1):

        #Distance by longitude and latitude; Haversine's formula
        lon1,lat1,lon2,lat2 = coordinates[x][0],coordinates[x][1],coordinates[x+1][0],coordinates[x+1][1]                           
        a = math.sin(math.radians(lat2-lat1)/2.0)**2+\
            math.cos(math.radians(lat1))*\
            math.cos(math.radians(lat2))*\
            math.sin(math.radians(lon2-lon1)/2.0)**2
        c=2*math.atan2(math.sqrt(a),math.sqrt(1-a))
        length+=6371000*c

        #Total altitude change
        height += coordinates[x+1][2] - coordinates[x][2]
    return [length,height]

class Route:
    def __init__(self,previous,distance):
        self.previous = previous
        self.distance = distance

class Vertex:
    def __init__(self,id,name,coordinates, category, connections, place):
        self.id = id
        self.name = name
        self.point = coordinates
        self.category = category
        self.connections = connections
        self.place = place

class Node:
    def __init__(self,id, points, coordinates, distance, forwards, reverse, covid, wheelchair, description):
        self.id = id
        self.start = points[0]
        self.end = points[1]
        self.points = coordinates
        self.length = distance[0]
        self.elevation = distance[1]
        self.distance = math.sqrt(distance[0]**2 + distance[1]**2)
        self.description = description
        self.covid = covid
        self.wheelchair = wheelchair
        self.forwards = forwards
        self.reverse = reverse

def login_view(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return HttpResponseRedirect(reverse('index'))
        else:
            return render(request, "website/login.html", {
                "message": "Invalid username and/or password."
            })
    else:
        return render(request, "website/login.html")

def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))

def register(request):
    if request.method == "POST":
        username = request.POST["username"]
        email = request.POST["email"]

        # Ensure password matches confirmation
        password = request.POST["password"]
        confirmation = request.POST["confirmation"]
        if password != confirmation:
            return render(request, "website/register.html", {
                "message": "Passwords must match."
            })

        # Attempt to create new user
        try:
            user = User.objects.create_user(username, email, password)
            user.save()
        except IntegrityError:
            return render(request, "website/register.html", {
                "message": "Username already taken."
            })
        login(request, user)
        return HttpResponseRedirect(reverse("index"))
    else:
        return render(request, "website/register.html")

def help(request, message = ''):
    if not request.user.is_authenticated:
        return login_view(request)
    if request.method == 'POST':
        port = 465  # For SSL
        smtp_server = "smtp.gmail.com"
        email = 'bradfieldgo@gmail.com'
        password = 'bradfieldgo1'
        sender_email = email
        receiver_email = email
        subject = request.POST['subject']
        message = request.POST['message']
        message = f"""\
            Subject: {subject}

        {message}"""
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, message)

        message = 'Your email has been sent!'
        return render(request, 'website/help.html', {'message': message})
    else:
        return render(request, 'website/help.html', {'message': message})
    
def index(request, message=''):
    if request.user.is_authenticated:
            k = kml.KML()
            doc = open("/Users/Gabriel/CODE/Pathfinders/BradfieldGo/bradfieldgo/website/static/website/BradfieldGo.kml").read()
            k.from_string(doc.encode('utf-8'))
            features = list(k.features())
            placemarks = list(features[0].features())

            vertexs = []
            nodes = []
            for item in placemarks:

                if item.geometry._type == 'LineString':
                    id,name,coordinates, description = item.id,item.name, item.geometry.coords, item.description
                    points = name.split('-')
                    distance = GetDistance(coordinates)
                    description = description.split('-')
                    code = description[0]
                    description.remove(code)
                    if 'W0' in code: wheelchair = False #not wheelchair accessible
                    elif 'W1' in code: wheelchair = True #wheelchair accessible
                    if 'C0' in code: covid = 'both' #both ways are fine in the one-way system
                    elif 'C1' in code: covid = 'forwards' #only the named way is fine in the one-way system
                    elif 'C2' in code: covid = 'reverse' #only the reverse way is fine in the one-way system
                    descriptionforwards, descriptionreverse = description[0], description[1]

                    newitem = Node(id,points,coordinates, distance, descriptionforwards, descriptionreverse , covid, wheelchair, description)
                    nodes.append(newitem)

            for item in placemarks:

                if item.geometry._type == 'Point':
                    connections = []
                    for node in nodes:
                        if node.start == item.name:
                            connections.append(node.end)
                        elif node.end == item.name:
                            connections.append(node.start)

                    id,name,coordinates,category = item.id,item.name, item.geometry.coords, item.description

                    place = name.split(' (')[0]

                    newitem = Vertex(id,name,coordinates[0], category, connections, place)
                    vertexs.append(newitem)

            vertexdict = {}
            types = []
            houses = []
            sports = []
            academics = []
            others = []
            for vertex in vertexs:
                vertexdict[vertex.name] = vertex
                if vertex.category.capitalize() not in types and vertex.category != 'turn' and vertex.category !='other':
                    types.append(vertex.category.capitalize())
                if vertex.category == 'house':
                        houses.append(vertex.place)
                elif vertex.category == 'sports':
                        sports.append(vertex.place)
                elif vertex.category == 'academic':
                        academics.append(vertex.place)
                elif vertex.category == 'other':
                        others.append(vertex.place)
            types.append('Other')

            places = []
            for vertex in vertexs:
                if vertex.category != 'turn':
                    places.append(vertex.place)

            houses = sorted(list(set(houses)))
            sports = sorted(list(set(sports)))
            academics = sorted(list(set(academics)))
            others = sorted(list(set(others)))
            places = sorted(list(set(places)))

            modes = ['Default','One Way System', 'Wheelchair','Wheelchair + One Way System']
            return render(request, 'website/index.html', {
                'points': places, 'categories': types, 'modes': modes, 'others': others, 
                'houses': houses, 'academics': academics, 'sports': sports, 'message': message,
            })
    else: 
        return login_view(request)

def go(request):
    if not request.user.is_authenticated:
        return login_view(request)
    if request.method == "POST":
        k = kml.KML()
        doc = open("/Users/Gabriel/CODE/Pathfinders/BradfieldGo/bradfieldgo/website/static/website/BradfieldGo.kml").read()
        k.from_string(doc.encode('utf-8'))
        features = list(k.features())
        placemarks = list(features[0].features())

        vertexs = []
        nodes = []
        for item in placemarks:
            id,name,coordinates, description = item.id,item.name, item.geometry.coords, item.description

            if item.geometry._type == 'LineString':
                points = name.split('-')
                distance = GetDistance(coordinates)
                description = description.split('-')
                code = description[0]
                description.remove(code)
                if 'W0' in code: wheelchair = False #not wheelchair accessible
                elif 'W1' in code: wheelchair = True #wheelchair accessible
                if 'C0' in code: covid = 'both' #both ways are fine in the one-way system
                elif 'C1' in code: covid = 'forwards' #only the named way is fine in the one-way system
                elif 'C2' in code: covid = 'reverse' #only the reverse way is fine in the one-way system
                descriptionforwards, descriptionreverse = description[0], description[1]

                newitem = Node(id,points,coordinates, distance, descriptionforwards, descriptionreverse , covid, wheelchair, description)
                nodes.append(newitem)

        for item in placemarks:
            id,name,coordinates,category = item.id,item.name, item.geometry.coords, item.description

            place = name.split(' (')[0]

            if item.geometry._type == 'Point':
                connections = []
                for node in nodes:
                    if node.start == item.name:
                        connections.append(node.end)
                    elif node.end == item.name:
                        connections.append(node.start)

                newitem = Vertex(id,name,coordinates[0], category, connections, place)
                vertexs.append(newitem)

        vertexdict = {}
        types = []
        houses = []
        sports = []
        academics = []
        others = []
        for vertex in vertexs:
            vertexdict[vertex.name] = vertex
            if vertex.category.capitalize() not in types and vertex.category != 'turn' and vertex.category !='other':
                types.append(vertex.category.capitalize())
            if vertex.category == 'house':
                houses.append(vertex.place)
            elif vertex.category == 'sports':
                sports.append(vertex.place)
            elif vertex.category == 'academic':
                academics.append(vertex.place)
            elif vertex.category == 'other':
                others.append(vertex.place)
        types.append('Other')

        places = []
        for vertex in vertexs:
            if vertex.category != 'turn':
                places.append(vertex.place)

        houses = sorted(list(set(houses)))
        sports = sorted(list(set(sports)))
        academics = sorted(list(set(academics)))
        others = sorted(list(set(others)))
        places = sorted(list(set(places)))

        start,end = request.POST["start"],request.POST["end"]
        midpoint1 = request.POST["midpoint1"]
        midpoint2 = request.POST["midpoint2"]
        midpoint3 = request.POST["midpoint3"]

        constraint = request.POST['modes']

        destinations = []
        startlist = []
        for vertex in vertexs:
            if vertex.place == start:
                startlist.append(vertex)
        destinations.append(startlist)
        ogstart = startlist

        midpoints = [midpoint1,midpoint2,midpoint3]

        for y in range(2):
            for midpoint in midpoints:
                if midpoint == 'none':
                    midpoints.remove(midpoint)

        for midpoint in midpoints:
            midpointlist = []
            for vertex in vertexs:
                if vertex.place == midpoint:
                    midpointlist.append(vertex)
            destinations.append(midpointlist)

        finishlist = []
        for vertex in vertexs:
            if vertex.place == end:
                finishlist.append(vertex)
        destinations.append(finishlist)

        for destination in destinations:
            for destination1 in destinations:
                if destination == destination1 and destinations[destinations.index(destination)] != destinations[destinations.index(destination1)]:
                    return HttpResponseRedirect(reverse('index'))

        modechoice = constraint
        if modechoice == 'Wheelchair' or modechoice == 'Wheelchair + One Way System':
            [nodes.remove(node) for node in nodes if node.wheelchair == False]
            wheelchair = True

        if modechoice == 'One Way System' or modechoice == 'Wheelchair + One Way System':
            oneway = True
        else:
            oneway = False

        nodenames = []
        for node in nodes:
            nodenames.append(f'{node.start}-{node.end}')

        fullroute = []
        totaldistance = 0
        for x in range(len(destinations)-1):
            startpos, endpos = destinations[x],destinations[x+1]
            comparisons = []
            for start in startpos:
              for end in endpos:
                previous, current = start, start
                searched, visited, fromsearched = [start.name], [start.name], [start.name]
                distances = {start.name:Route(previous,0)}
                Continue = True
                while Continue:
                    for connection in current.connections:
                      if f'{current.name}-{connection}' in nodenames or f'{connection}-{current.name}' in nodenames:
                        position = vertexdict[connection]
                        previous = current
                        if oneway:
                                olddistance = distances[previous.name].distance
                                nextforwards = [node for node in nodes if (node.start == current.name and node.end == connection)]
                                if nextforwards == []:
                                    nextreverse = [node for node in nodes if (node.start == connection and node.end == current.name)]
                                    if nextreverse[0].covid == 'reverse' or nextreverse[0].covid == 'both':
                                        distance = nextreverse[0].distance
                                    else:
                                        distance = 9999999999
                                else:
                                    if nextforwards[0].covid == 'forwards' or nextforwards[0].covid == 'both':
                                        distance = nextforwards[0].distance
                                    else:
                                        distance = 9999999999
                                newdistance = olddistance + distance

                        else:
                            olddistance = distances[previous.name].distance
                            distance = [node for node in nodes if (node.start == connection and node.end == current.name) or (node.start == current.name and node.end == connection)][0].distance
                            newdistance = olddistance + distance

                        if position.name in visited:
                            if distances[position.name].distance > newdistance:
                                distances.pop(position.name)
                                distances[position.name] = Route(previous,newdistance)
                                if position.name in searched:
                                    searched.remove(position.name)
                        else:
                            distances[position.name] = Route(previous,newdistance)
                            visited.append(position.name)
                    try:
                        Random = [choice for choice in visited if choice not in searched]
                        current = vertexdict[random.choice(Random)]
                        searched.append(current.name)
                    except IndexError:
                        Continue = False
        
                route = [end]
                current = end
                try:
                    currentprevious = distances[current.name].previous
                except KeyError:
                    modes = ['Default','One Way System', 'Wheelchair','Wheelchair + One Way System']
                    message = 'Unfortunately, this path is not possible with your constraint.'
                    return render(request, 'website/index.html', {
                        'points': places, 'categories': types, 'modes': modes, 'others': others, 
                        'houses': houses, 'academics': academics, 'sports': sports, 'message': message,
                    })
                while currentprevious != start:
                    route.append(distances[current.name].previous)
                    current = [vertex for vertex in vertexs if distances[current.name].previous.name == vertex.name][0]
                    currentprevious = distances[current.name].previous

                if (start == ogstart[0] and start == startpos[0]):
                    route.append(start)
                try:
                    if (start == ogstart[1] and start == startpos[1]):
                        route.append(start)
                except IndexError:
                    pass
                
                comparisons.append([start,end,distances[end.name].distance,route])

            distancecomparison = []
            for comparison in comparisons:
                distancecomparison.append(comparison[2])

            firstdistance = sorted(distancecomparison)[0]
            for comparison in comparisons:
                if firstdistance == comparison[2]:
                    start = comparison[0]
                    end = comparison[1]
                    distance = comparison[2]
                    route = comparison[3]
                    break
            
            route = route[::-1]
            distance = distances[end.name].distance
            totaldistance += distance
            fullroute.append(route)
        route = list(itertools.chain.from_iterable(fullroute))
        paths = []
        descriptions = []
        totalelevation = 0
        upwards = 0
        for x in range(len(route)-1):
            node = [node for node in nodes if (node.start == route[x].name and node.end == route[x+1].name) or (node.start == route[x+1].name and node.end == route[x].name)][0]
            if node.start == route[x].name and node.end == route[x+1].name:
                description = node.forwards
                height = node.elevation
            elif node.start == route[x+1].name and node.end == route[x].name:
                description = node.reverse
                height = node.elevation*-1
            paths.append([f'{node.start}-{node.end}',node.points, description])
            descriptions.append(description)
            totalelevation += height
            if height > 0:
                upwards += height

        minutes = ((totaldistance/1000)*12)+(upwards/10)
        minute = math.floor(minutes)
        seconds = round((minutes-minute)*60)
        if seconds < 10:
            seconds = f'0{seconds}'
        time = f'{minute}:{seconds}'

        kml1 = simplekml.Kml()
        points = []
        destinationsfinal = []
        for destination in destinations:
            for place in destination:
                if place in route:
                    destinationsfinal.append(place)
                    points.append(place)

        for place in points:
            kml1.newpoint(name=place.name, coords=[place.point])

        for path in paths:
            kml1.newlinestring(name=path[0], coords=path[1], description=path[2])

        code = 1
        while os.path.exists(f"/Users/Gabriel/CODE/Pathfinders/BradfieldGo/bradfieldgo/website/static/website/images/BradfieldGo{code}.png"):
            code += 1
            if code == 1000:
                code = 1
                break
        kml1.save(f"/Users/Gabriel/CODE/Pathfinders/BradfieldGo/bradfieldgo/website/static/website/paths/Path{code}.kml")

        for description in descriptions:
            if description == 'Nothing':
                descriptions.remove(description)

        km = kml.KML()
        doc = open(f"/Users/Gabriel/CODE/Pathfinders/BradfieldGo/bradfieldgo/website/static/website/paths/Path{code}.kml").read()
        km.from_string(doc.encode('utf-8'))
        features = list(km.features())
        placemarks = list(features[0].features())

        items = []
        for item in placemarks:
            name,coordinates = item.name, item.geometry.coords

            if len(coordinates) == 1:
                points = GetPosition(coordinates[0])
                items.append(points)

            else:
                linepoints = []
                for coordinate in coordinates:
                    points = GetPosition(coordinate)
                    linepoints.append(points)
                items.append(linepoints)

        with Image.open("/Users/Gabriel/CODE/Pathfinders/BradfieldGo/bradfieldgo/website/static/website/BradfieldGo.png") as im:

            left, right, top, bottom = 2000,0,0,2000
            draw = ImageDraw.Draw(im)
            for item in items:
                if type(item[0]) == list:
                    for point in item:
                        if point[0] < left:
                            left = point[0]
                        elif point[0] > right:
                            right = point[0]
                        if point[1] < bottom:
                            bottom = point[1]
                        elif point[1] > top:
                            top = point[1]
                    item = list(itertools.chain.from_iterable(item))
                    draw.line(item, fill='white', width=4)

            for item in items:
                if type(item[0]) != list:
                    if item[0] < left:
                        left = item[0]
                    elif item[0] > right:
                        right = item[0]
                    if item[1] < bottom:
                        bottom = item[1]
                    elif item[1] > top:
                        top = item[1]
                    draw.ellipse((item[0]-10, item[1]-10, item[0]+10, item[1]+10), fill = 'green', outline ='white')
            destinations1 = destinationsfinal.pop(-1)

            if (top-bottom) < 450 or (right-left) < 600:
                im = im.crop((left-150, bottom-150, right+150, top+150))
            elif (top-bottom) < 600 or (right-left) < 900:
                im = im.crop((left-100, bottom-100, right+100, top+100))
            elif (top-bottom) < (right-left):
                im = im.crop((left-30, bottom-30, right+30, top+30))
            else:
                height = top-bottom
                im = im.crop((left-30-height/2, bottom-30, right+30+height/2, top+30))

            source = f"website/images/BradfieldGo{code}.png"
            im.save(f"/Users/Gabriel/CODE/Pathfinders/BradfieldGo/bradfieldgo/website/static/website/images/BradfieldGo{code}.png")
        os.remove(f"/Users/Gabriel/CODE/Pathfinders/BradfieldGo/bradfieldgo/website/static/website/paths/Path{code}.kml")
        return render(request, 'website/go.html', {
            'descriptions': descriptions, "route": route, "source": source, 'end': destinations1, 'time': time,
            'distance': round(totaldistance), 'elevation': round(totalelevation), 'destinations': destinationsfinal,
            })
    else:
        return HttpResponseRedirect(reverse('index'))