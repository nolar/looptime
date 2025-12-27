# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import os

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'looptime'
copyright = '2021-2025 Sergey Vasilyev'
author = 'Sergey Vasilyev'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.extlinks',
    'sphinx.ext.linkcode',
    'sphinx.ext.intersphinx',
    'sphinx.ext.todo',
    'sphinx_llm.txt',
]

html_theme = 'furo'
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
html_static_path = []
templates_path = []

# -- Options for intersphinx extension ---------------------------------------
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}

# -- Options for linkcode extension ------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/linkcode.html

def linkcode_resolve(domain, info):
    if domain != 'py':
        return None
    if not info['module']:
        return None
    filename = info['module'].replace('.', '/')
    return "https://github.com/nolar/looptime/blob/main/%s.py" % filename

# -- Options for extlinks extension ------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/extlinks.html

extlinks = {
    'issue': ('https://github.com/nolar/looptime/issues/%s', 'issue %s'),
}

###############################################################################
# Ensure the apidoc is always built as part of the build process,
# especially in ReadTheDocs build environment.
# See: https://github.com/rtfd/readthedocs.org/issues/1139
###############################################################################

def run_apidoc(_):
    ignore_paths = [
    ]

    docs_path = os.path.relpath(os.path.dirname(__file__))
    root_path = os.path.relpath(os.path.dirname(os.path.dirname(__file__)))

    argv = [
        '--force',
        '--no-toc',
        '--separate',
        '--module-first',
        '--output-dir', os.path.join(docs_path, 'packages'),
        os.path.join(root_path, 'looptime'),
    ] + ignore_paths

    from sphinx.ext import apidoc
    apidoc.main(argv)


def setup(app):
    app.connect('builder-inited', run_apidoc)
