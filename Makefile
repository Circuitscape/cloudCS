VER=0.0.1

pypi: clean
	python setup.py sdist

pypi_upload: clean
	python setup.py sdist upload

pypi_register: clean
	python setup.py register

clean:
	rm -fr *~ *# *.pyc
	mkdir -p output

cleanall: clean
	rm -fr dist build output 
	mkdir -p output
	
