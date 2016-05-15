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
def insert_local(folder='imgs'):
    for filename in get_all_imgs(folder):
        if not accept(filename):
            print("{} not accepted".format(filename))
            continue
        url = '{LOCAL}/' + filename
        db.session.add(Image(url=url))
        print("Adding {}...".format(filename))
    db.session.commit()

def accept(filename):
    val = imread(filename).sum()
    if val > 0:
        return True
    else:
        return False
