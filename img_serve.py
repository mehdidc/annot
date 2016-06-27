#!/bin/python
import re
import os
from flask import Flask, Response, request, abort, render_template_string, send_from_directory
from PIL import  Image
import StringIO

app = Flask(__name__)

DEBUG = True
WIDTH = 1000
HEIGHT = 800

TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <style>
    p{
        text-align: center;
    }
    img{
    }
    </style>
</head>
<body>
    {% for image in images %}
        <p>
        <img src='/{{ image.src }}' />
        </p>
    {% endfor %}
</body>
'''

@app.route('/<path:filename>')
def image(filename):
    try:
        w = int(request.args['w'])
        h = int(request.args['h'])
    except (KeyError, ValueError):
        return send_from_directory('.', filename)

    try:
        im = Image.open(filename)
        im.thumbnail((w, h), Image.ANTIALIAS)
        io = StringIO.StringIO()
        im.save(io, format='JPEG')
        return Response(io.getvalue(), mimetype='image/jpeg')

    except IOError:
        abort(404)

    return send_from_directory('.', filename)

def get_all_imgs(folder='.', pattern=''):
    regexp = re.compile(pattern)
    for root, dirs, files in os.walk(folder, followlinks=True):
        for filename in [os.path.join(root, name) for name in files]:
            if not filename.endswith('.jpg') and not filename.endswith('.png'):
                continue
            if not regexp.search(filename):
                continue
            yield filename

@app.route('/pattern/<pattern>')
def index(pattern):
    list_filenames = get_all_imgs('.', pattern=pattern)
    images = get_images(list_filenames)
    return render_template_string(TEMPLATE, **{
        'images': images
    })


@app.route('/bookmark/<filename>')
def bookmark(filename):
    images = []
    for pattern in open(filename).readlines():
        pattern = pattern[0:-1]
        list_filenames = get_all_imgs('.', pattern=pattern)
        images.extend(get_images(list_filenames))
    return render_template_string(TEMPLATE, **{
        'images': images
    })


def get_images(filenames):
    images = []
    for filename in filenames:
        try:
            im = Image.open(filename)
            w, h = im.size
            aspect = 1.0*w/h
            if aspect > 1.0*WIDTH/HEIGHT:
                width = min(w, WIDTH)
                height = width/aspect
            else:
                height = min(h, HEIGHT)
                width = height*aspect
            images.append({
                'width': int(width),
                'height': int(height),
                'src': filename
            })
        except Exception:
            continue
    return images


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='WebServer')
    parser.add_argument("--host",
                        type=str,
                        default="0.0.0.0")
    parser.add_argument("--port",
                        type=int,
                        default=5000)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=DEBUG)
