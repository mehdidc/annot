import os
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from flask import render_template
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker, relationship
from  sqlalchemy.sql.expression import func, select


DEBUG = True
IMG_SERVER = 'http://localhost:5001'

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
                db.session.add(Match(left_id=winner, right_id=loser, experiment=experiment))
                db.session.commit()

        img1, img2 = selector()
        return render_template('template.html', 
                               url1=parse(img1.url), url2=parse(img2.url), 
                               id1=img1.id, id2=img2.id,
                               experiment=name)
    return page_gen

def parse(url):
    return url.format(LOCAL=IMG_SERVER)

@app.route('/matches/')
def matches():
    experiment = request.args.get('experiment')
    if experiment is not None:
        matches = Match.query.filter_by(experiment=experiment)
    else:
        matches = Match.query.all()
    return render_template('matches.html', matches=matches)

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
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=DEBUG)
