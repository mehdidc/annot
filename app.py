import os
from collections import defaultdict
from flask import Flask, request, redirect, render_template, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker, relationship
from  sqlalchemy.sql.expression import func, select
from sqlalchemy.orm import aliased

from flask.ext.sqlalchemy_cache import CachingQuery
from flask.ext.sqlalchemy_cache import FromCache
from flask.ext.sqlalchemy import SQLAlchemy, Model

from flask.ext.cache import Cache

from trueskill import Rating, quality_1vs1, rate_1vs1
from itertools import product
import random
import numpy as np

def get_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('google.com', 0))
    ip = s.getsockname()[0]
    return ip

DEBUG = True
IMG_SERVER = 'http://{}:5001'.format(get_ip())

app = Flask(__name__)
db_filename = 'data.db'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{}'.format(db_filename)
#app.config['CACHE_TYPE'] = 'memcached'

Model.query_class = CachingQuery
db = SQLAlchemy(app, session_options={'query_cls': CachingQuery})

cache = Cache(app)

class Match(db.Model):
    __tablename__ = 'Match'
    id = db.Column(db.Integer, primary_key=True)
    left_id = db.Column(db.Integer, ForeignKey('Image.id'))
    right_id = db.Column(db.Integer, ForeignKey('Image.id'))
    datetime = Column(DateTime, default=func.now())
    experiment =  db.Column(db.String(50))
    ip = db.Column(db.String(50))

    left = relationship('Image', foreign_keys='Match.left_id')
    right = relationship('Image', foreign_keys='Match.right_id')

class Image(db.Model):
    __tablename__ = 'Image'

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(200), unique=True)

    def __repr__(self):
        return '<Image {}>'.format(self.url)

def random_selector(pattern='%', name='random'):

    def selector_():
        q = Image.query.filter(Image.url.like(pattern))
        img1, img2 = q.order_by(func.random()).limit(2)
        return img1, img2
    selector_.__name__ = name
    return selector_

def fair_selector(pattern='%', name='fair', thresh=0.5, percentile=90):
    def selector_():
        import time
        image_alias = aliased(Image)
        matches = Match.query
        matches = matches.options(FromCache(cache))
        matches = matches.join(Match.left).join(image_alias, Match.right)
        matches = matches.filter(Image.url.like(pattern))
        matches = matches.filter(image_alias.url.like(pattern))

        t = time.time()
        images = [(match.left, match.right) for match in matches]
        print(time.time() - t)

        t = time.time()
        matches_urls = [(left.url, right.url) for left, right in images]
        print(time.time() - t)

    
        t = time.time()
        score = get_scores(images)
        print(time.time() - t)

        percentile_val = np.percentile(score.values(), percentile)
        urls = score.keys()
        urls = filter(lambda url:score[url] > percentile_val, urls)
        t = time.time()
        rating = get_rating(images)
        print(time.time() - t)

        t = time.time()
        match = list(product(urls, urls))
        random.shuffle(match)
        for left, right in match:
            f = get_fairness(rating, left, right)
            if f >= thresh:
                break
        print(time.time() - t)
        return left, right
    selector_.__name__ = name
    return selector_

def build_experiment(name='', question='Which one do you prefer?', selectors=None, w=200, h=200):
    if selectors is None:
        selectors = [random_selector]
    def page_gen(selector):
        if request.method == 'POST':
            winner = request.form['winner']
            loser = request.form['loser']
            experiment = request.form['experiment']
            if winner and loser and experiment:
                winner = int(winner)
                loser = int(loser)
                print('Adding a match...')
                db.session.add(Match(left_id=winner, right_id=loser, experiment=experiment, ip=request.remote_addr))
                db.session.commit()
        selector = selector.replace('/', '')
        print(selector)
        for select in selectors:
            if select.__name__ == selector:
                img1, img2 = select()
                break
        return render_template('template.html', 
                               url1=parse(img1.url), url2=parse(img2.url), 
                               id1=img1.id, id2=img2.id,
                               question=question,
                               w=w,
                               h=h,
                               experiment=name)
    
    sel_name = selectors[0].__name__
    def page_gen_default():
        return page_gen(sel_name)
    page_gen_default.__name__ = name + '_default'

    page_gen.__name__ = name
    addr = '/' + name + '/<string:selector>/'
    page_gen = app.route(addr, methods=['GET', 'POST'])(page_gen)
    addr = '/'+ name + '/'
    page_gen_default = app.route(addr, methods=['GET', 'POST'])(page_gen_default)
    return page_gen

def parse(url):
    return url.format(LOCAL=IMG_SERVER)
app.jinja_env.filters['parse_url'] = parse

@app.route('/matches/')
def matches():
    experiment = request.args.get('experiment')
    if experiment is not None:
        matches = Match.query.filter_by(experiment=experiment)
    else:
        matches = Match.query.all()
    return render_template('matches.html', matches=matches)

@app.route('/ranks/')
def ranks():
    experiment = request.args.get('experiment')
    if experiment is None:
        matches = None
    else:
        matches = Match.query.filter_by(experiment=experiment)
    urls, scores = get_urls_and_scores(matches)
    return render_template('rank.html', rank_url_score=zip(range(1, len(urls) + 1), urls, scores))

def get_urls_and_scores(matches=None):
    matches = get_matches_urls(matches)
    score = get_scores(matches)
    urls = sorted(score.keys(), key=lambda url: -score[url])
    scores = map(lambda url:score[url], urls)
    urls = map(parse, urls)
    return urls, scores


def get_matches_images(matches=None):
    if matches is None:
        matches = Match.query.all()
    matches = [(match.left, match.right) for match in matches]
    return matches

def get_matches_urls(matches=None):
    if matches is None:
        matches = Match.query.all()
    matches = [(match.left.url, match.right.url) for match in matches]
    return matches

def get_scores(matches):
    rating = get_rating(matches)
    return {el: r.mu - 2 * r.sigma for el, r in rating.items()}

def get_rating(matches):
    rating = defaultdict(lambda: Rating())
    for winner, loser in matches:
        rating[winner], rating[loser] = rate_1vs1(rating[winner], rating[loser])
    return rating

def get_fairness(rating, url1, url2):
    return quality_1vs1(rating[url1], rating[url2])

innovative = build_experiment(
        name='innovative', 
        question='Which one is more innovative ? ',
        selectors=[random_selector('%models_mini%', name='random'),
                   fair_selector('%models_mini%', name='fair', thresh=0.5, percentile=90)])

existing = build_experiment(
        name='existing', 
        question='Which one looks more like existing digits?',
        selectors=[random_selector('%models_mini%', name='random'),
                   fair_selector('%models_mini%', name='fair', thresh=0.5, percentile=90)])

fixating = build_experiment(
        name='fixating', 
        question='Which one is fixating more?',
        selectors=[random_selector('%models_mini%', name='random'),
                   fair_selector('%models_mini%', name='fair', thresh=0.5, percentile=90)])

noisy = build_experiment(
        name='noisier', 
        question='Which one is noisier ?',
        selectors=[random_selector('%models_mini%', name='random'),
                   fair_selector('%models_mini%', name='fair', thresh=0.5, percentile=90)])


gan = build_experiment(
        name='gan', 
        question='Which one is more good looking/realistic ?',
        selectors=[random_selector('%gan/%', name='random'),
                   fair_selector('%gan%', name='fair', thresh=0.5, percentile=90)],
        w=800,
        h=800)

@app.route('/')
def index():
    page_name = 'innovative'
    selector = 'random'
    return redirect(url_for(page_name, selector=selector)) 

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='WebServer')
    parser.add_argument("--config-module",
                        type=str, help="config filename",
                        default="config")
    parser.add_argument("--host",
                        type=str,
                        default="0.0.0.0")
    parser.add_argument("--port",
                        type=int,
                        default=5000)
    parser.add_argument("--imgserver",
                        type=str,
                        default=IMG_SERVER)
    args = parser.parse_args()
    IMG_SERVER = args.imgserver
    app.run(host=args.host, port=args.port, debug=DEBUG, threaded=True)
