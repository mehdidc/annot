import os

from skimage.io import imread
from invoke import task
from app import db, Image, Match, User, Classification
from img_serve import get_all_imgs
from sqlalchemy import distinct


@task
def create_db(ctx):
    #Classification.__table__.drop(db.engine)
    db.create_all()
    User.new(name='admin', pwd='admin')
    User.new(name='kegl', pwd='kegl')
    User.new(name='mehdi', pwd='mehdi')


@task
def insert_urls(ctx, filename):
    for i, url in enumerate(open(filename).readlines()):
        url = url[0:-1]
        db.session.add(Image(url=url))
    db.session.commit()

@task
def insert_local(ctx, folder='imgs', pattern=''):
    for filename in get_all_imgs(folder, pattern=pattern):
        if not accept(filename):
            print("{} not accepted".format(filename))
            continue
        url = '{LOCAL}/' + filename
        try:
            db.session.add(Image(url=url))
            print("Adding {}...".format(filename))
            db.session.commit()
        except Exception as ex:
            db.session.rollback()
            print("Exception : {}, ignoring {}".format(ex, filename))

@task
def remove(ctx, pattern=''):
    q = Image.query.filter(Image.url.like(pattern))
    print('nb deleted : {}'.format(q.delete(synchronize_session=False)))
    db.session.commit()

@task
def remove_matches(ctx, experiment=''):
    q = Match.query.filter(Match.experiment==experiment)
    q.delete(synchronize_session=False)
    db.session.commit()

@task
def experiments(ctx):
    q = db.session.query(distinct(Match.experiment))
    q = list(q)
    print(q)

def accept(filename):
    val = imread(filename).sum()
    if val > 0:
        return True
    else:
        return False
