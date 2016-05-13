import os
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from flask import render_template
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker, relationship
from  sqlalchemy.sql.expression import func, select


DEBUG = True

app = Flask(__name__)
db_filename = 'data.db'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{}'.format(db_filename)
db = SQLAlchemy(app)


class Match(db.Model):
    __tablename__ = 'Match'
    id = db.Column(db.Integer, primary_key=True)
    left_id = db.Column(db.Integer, ForeignKey('Image.id'))
    right_id = db.Column(db.Integer, ForeignKey('Image.id'))

    left = relationship('Image', foreign_keys='Match.left_id')
    right = relationship('Image', foreign_keys='Match.right_id')


class Image(db.Model):
    __tablename__ = 'Image'

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(200))

    def __repr__(self):
        return '<Image {}>'.format(self.url)

@app.route('/', methods=['GET', 'POST'])
def index():

    if request.method == 'POST':
        winner = request.form['winner']
        loser = request.form['loser']
        if winner and loser:
            winner = int(winner)
            loser = int(loser)
            print('adding a match...')
            db.session.add(Match(left_id=winner, right_id=loser))
            db.session.commit()

    img1, img2 = Image.query.order_by(func.random()).limit(2)
    return render_template('template.html', 
                           url1=img1.url, url2=img2.url, 
                           id1=img1.id, id2=img2.id)

@app.route('/matches')
def matches():
    matches = Match.query.all()
    print(matches)
    return render_template('matches.html', matches=matches)


if __name__ == '__main__':
    import argparse

    if not os.path.exists(db_filename):
        db.create_all()
        nb = 100
        for i, url in enumerate(open('urls').readlines()):
            if i == nb:
                break
            url = url.replace('\n', '').replace('\t', ' ').split(' ', 2)[1]
            print(url)
            db.session.add(Image(url=url))
        db.session.commit()
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
