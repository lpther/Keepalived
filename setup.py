from distribute_setup import use_setuptools
use_setuptools()

from setuptools import setup


setup(
    name='keepalived',
    version='0.1.0',
    author='Louis-Philippe Theriault',
    author_email='lpther@gmail.com',
    packages=['keepalived'],
    url='https://github.com/lpther/Keepalived.git',
    license='See LICENSE.txt',
    description='',
    long_description=open('README.txt').read(),
)
