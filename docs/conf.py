import os
import sys
from os.path import dirname

# For conversion from markdown to html
# set paths
docs = dirname(dirname(__file__))
root = dirname(docs)
sys.path.insert(0, root)
sys.path.insert(0, os.path.join(docs, "sphinxext"))

# -- General configuration ------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "autodoc_traits",
    "myst_parser",
    "m2r",
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# Set the default role so we can use `foo` instead of ``foo``
default_role = "literal"

# source_suffix = [".rst", ".md"]
source_suffix = []

# The root toctree document.
root_doc = master_doc = "index"

# General information about the project.
project = "JupyterHub Outpost"
copyright = "2023, Forschungszentrum Juelich GmbH"
author = "Tim Kreuzer"

release = "0.2.5"

language = None

exclude_patterns = ["build", "Thumbs.db", ".DS_Store"]

pygments_style = "sphinx"

todo_include_todos = False


# -- MyST configuration ------------------------------------------------------
# ref: https://myst-parser.readthedocs.io/en/latest/configuration.html
#
myst_enable_extensions = [
    # available extensions: https://myst-parser.readthedocs.io/en/latest/syntax/optional.html
    "colon_fence",
]


# -- Options for HTML output ----------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "sphinx_book_theme"
html_title = "JupyterHub Outpost"

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
#
html_theme_options = {
    "repository_url": "https://github.com/kreuzert/jupyterhub-outpost",
    "use_issues_button": True,
    "use_repository_button": True,
    "use_edit_page_button": True,
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]


# Example configuration for intersphinx: refer to the Python standard library.
intersphinx_mapping = {"https://docs.python.org/": None}
