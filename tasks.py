import os

from skimage.io import imread
from invoke import task
from app import db, Image
from img_serve import get_all_imgs

@task
def create_db():
    db.create_all()

@task
def insert_urls(filename):
    for i, url in enumerate(open(filename).readlines()):
        url = url[0:-1]
        db.session.add(Image(url=url))
    db.session.commit()

@task
def insert_local(folder='imgs', pattern=''):
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
def remove(pattern=''):
    q = Image.query.filter(Image.url.like(pattern))
    print('nb deleted : {}'.format(q.delete(synchronize_session=False)))
    db.session.commit()

def accept(filename):
    val = imread(filename).sum()
    if val > 0:
        return True
    else:
        return False
