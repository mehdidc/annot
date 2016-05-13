import os

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
def insert_local():
	for filename in get_all_imgs('.'):
		url = '{LOCAL}/' + filename
		try:
			db.session.add(Image(url=url))
			db.session.commit()
		except Exception as ex:
			print(ex, filename)
