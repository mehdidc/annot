import os
from collections import defaultdict
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from flask import render_template
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker, relationship
from  sqlalchemy.sql.expression import func, select
from trueskill import Rating, quality_1vs1, rate_1vs1

def get_ip():
    import socket
    hostname = socket.gethostname()
    return hostname

DEBUG = True
IMG_SERVER = 'http://{}:5001'.format(get_ip())

app = Flask(__name__)
db_filename = 'data.db'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{}'.format(db_filename)
db = SQLAlchemy(app)


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

def random_selector():
    img1, img2 = Image.query.order_by(func.random()).limit(2)
    return img1, img2

def build_experiment(name='', addr='', selector=None):
    if addr == '':
        addr = name
    if selector is None:
        selector = random_selector

    @app.route('/' + addr, methods=['GET', 'POST'])
    def page_gen():

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

        img1, img2 = selector()
        return render_template('template.html', 
                               url1=parse(img1.url), url2=parse(img2.url), 
                               id1=img1.id, id2=img2.id,
                               experiment=name)
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
    urls = [image.url for image in Image.query.all()]
    matches = Match.query.all()
    matches = [(match.left.url, match.right.url) for match in matches]
    score = get_scores(matches)
    urls = sorted(score.keys(), key=lambda url: -score[url])
    scores = map(lambda url:score[url], urls)
    urls = map(parse, urls)
    return render_template('rank.html', rank_url_score=zip(range(1, len(urls) + 1), urls, scores))

def get_scores(matches):
    rating = defaultdict(lambda: Rating())
    for winner, loser in matches:
        rating[winner], rating[loser] = rate_1vs1(rating[winner], rating[loser])
    return {el: r.mu - 2 * r.sigma for el, r in rating.items()}

random_selection = build_experiment(name='random', selector=random_selector)

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
    app.run(host=args.host, port=args.port, debug=DEBUG)
