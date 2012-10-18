import copy
import errno
import fnmatch
import glob
import os
import pypandoc
import shutil

from cement.core import controller, foundation, backend
from collections import defaultdict
from jinja2 import Environment, PackageLoader

template_env = Environment(loader=PackageLoader('manchego', 'templates'))


def require_dir(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise

def get_doc_title(content_lines, default="untitled"):
    title = iter(content_lines).next().strip()
    # this directive is specific to Pandoc-flavour-Markdown:
    if not title.startswith('% '):
        return default
    return re.sub(r'^%\s+', '', title)

FILE_EXTENSIONS = {
    'rst': 'rst',
    'markdown': 'md',
    # etc
}


class Tree(defaultdict):
    def __init__(self, attribute_name='value', attribute_factory=lambda:None, **kwargs):
        super(Tree, self).__init__(lambda: Tree(attribute_name, attribute_factory))
        setattr(self, attribute_name, kwargs.get(attribute_name, attribute_factory()))

def deep_get(tree, key_list):
    this_tree = tree
    for key in key_list:
        this_tree = this_tree[key]
    return this_tree


_no_deeper = lambda t: (not t.keys() and not t.files)

def get_leaves(tree):
    for key, sub_tree in tree.items():
        if _no_deeper(sub_tree):
            yield tree, key
        else:
            for sub_sub_tree, sub_key in get_leaves(sub_tree):
                yield sub_sub_tree, sub_key


class ManchegoFileTree(object):
    def __init__(self, pattern, ignore_names=None, ignore_paths=None):
        self._tree = Tree('files', list)
        self.pattern = pattern
        self.basepath = ''
        self.ignore_names = ignore_names or []
        self.ignore_paths = ignore_paths or []

    @property
    def tree(self):
        return self._tree

    def _iter_files(self, files):
        for basename in files:
            if basename not in self.ignore_names and fnmatch.fnmatch(basename, self.pattern):
                yield basename

    def path_stub(self, path):
        return path[len(self.basepath)+1:]

    def _prune(self, tree, parent_tree=None, parent_key=None):
        # delete bare leaves
        for parent_tree, parent_key in get_leaves(self.tree):
            if parent_tree and parent_key in parent_tree:
                del parent_tree[parent_key]

    def construct(self, root_path, file_info_func=lambda *args: tuple(args)):
        self.basepath = os.path.abspath(root_path)# source files to read from
        for root, dirs, files in os.walk(root_path):
            if root in self.ignore_paths:
                continue

            stub = self.path_stub(os.path.abspath(root))
            ftree = deep_get(self.tree, stub.split(os.sep))
            
            for basename in self._iter_files(files):
                src_filename = os.path.join(root, basename)
                ftree.files.append(file_info_func(root, src_filename))
        print 'CONSTRUCT ****', id(self.tree)
        self._prune(self.tree)
        print list(get_leaves(self.tree))


class ManchegoApp(foundation.CementApp):
    _defaults = {
        'manchego': {
            'file_pattern': '*.md',
            'toc_file': 'index.rst',
            'toc_template': 'toc.rst',
            'output_dir': './docs',
            'from_format': 'markdown',
            'to_format': 'rst',
        }
    }
    _arguments = [
        (['-od', '--outputdir'], {
            'action': 'store',
            'dest': 'output_dir',
            'help': 'Output path (absolute, or relative to current dir)'
         }),
        (['-p', '--pattern'], {
            'action': 'store',
            'dest': 'file_pattern',
            'help': 'Convert files that match this glob-style (not regex) pattern'
         }),
        (['-c', '--toc'], {
            'action': 'store',
            'dest': 'toc_file',
            'help': 'Name of the '
         }),
        (['-f', '--from'], {
            'action': 'store',
            'dest': 'from_format',
            'help': 'Format of source files, to convert from'
         }),
        (['-t', '--to'], {
            'action': 'store',
            'dest': 'to_format',
            'help': 'Format of destination files, to convert to'
         }),
        (['--dry-run'], {
            'action': 'store_true',
            'dest': 'dry_run',
            'help': "Don't write any files"
         }),
        (['input_dir'], {
            'action': 'store',
            'help': 'Path to root dir of source files'
         }),
    ]

    def __init__(self, label=None, **kwargs):
        if 'config_defaults' not in kwargs:
            kwargs['config_defaults'] = copy.copy(self._defaults)
        else:
            defaults = copy.copy(self._defaults)
            defaults.update(kwargs['config_defaults'])
            kwargs['config_defaults'] = defaults

        if 'arguments_override_config' not in kwargs:
            kwargs['arguments_override_config'] = True
        
        super(ManchegoApp, self).__init__(label, **kwargs)

    def setup(self):
        super(ManchegoApp, self).setup()
        for _args,_kwargs in self._arguments:
            self.args.add_argument(*_args, **_kwargs)

    def run(self):
        super(ManchegoApp, self).run()
        file_pattern = self.config.get('manchego', 'file_pattern')
        from_format = self.config.get('manchego', 'from_format')
        to_format = self.config.get('manchego', 'to_format')
        output_dir = self.config.get('manchego', 'output_dir')
        toc_file = self.config.get('manchego', 'toc_file')
        toc_template = self.config.get('manchego', 'toc_template')

        # TODO
        ignore_names = None
        ignore_paths = None

        basepath = os.path.abspath(self.pargs.input_dir)

        def file_info(path, filename):
            path_stub = path[len(basepath)+1:]# eg 'kitchen/cookbooks/xxx' (not a full relative or absolute path)
            output_subdir = os.path.join(output_dir, path_stub)

            output_path = "%s.%s" % (os.path.splitext(os.path.join(output_subdir, os.path.basename(filename)))[0],
                                     FILE_EXTENSIONS[to_format])
            
            # convert and save the doc
            converted_doc = pypandoc.convert(filename, to_format, format=from_format)
            tmp_file = os.tmpfile()
            tmp_file.write(converted_doc)
            # "will be automatically deleted once there are no file descriptors for the file"

            return {
                'source_path': filename,
                'output_path': output_path,
                'tmp_file': tmp_file,
                'title': get_doc_title(converted_doc,
                                       "%s: %s" % (path_stub,
                                                   os.path.splitext(os.path.basename(filename))[0]))
            }

        doc_tree = ManchegoFileTree(file_pattern, ignore_names=ignore_names, ignore_paths=ignore_paths)
        doc_tree.construct(basepath, file_info)

        # generate TOCs for each path in output_dir
        template = template_env.get_template(toc_template)

        def generate_toc(base_path, base_tree, title='Generated TOC'):
            template_data = {
                'title': title,
            }

            for path_segment, sub_tree in base_tree.items():
                # generate sub-TOCs:
                this_path = os.path.join(base_path, path_segment)
                generate_toc(this_path, sub_tree)

            # list sub dirs:
            template_data['items'] = base_tree.keys()# TODO: prune empty trees
            template_data['files'] = []

            # following content in the TOC:
            if len(base_tree.files) == 1:
                # bring the lone file content into the TOC
                template_data['title'] = base_tree.files[0]['title']
                template_data['content'] = base_tree.files[0]['tmp_file'].read()
                # cleanup:
                base_tree.files[0]['tmp_file'].close()
                del base_tree.files[0]['tmp_file']
            else:
                for tree_file in base_tree.files:
                    template_data['files'].append(os.path.splitext(os.path.basename(tree_file['output_path']))[0])
                    # copy temp file to output dir
                    if not self.pargs.dry_run:
                        require_dir(os.path.dirname(tree_file['output_path']))
                        with open(tree_file['output_path'], 'w') as output_file:
                            shutil.copyfileobj(tree_file['tmp_file'], output_file)
                    # cleanup:
                    tree_file['tmp_file'].close()
                    del tree_file['tmp_file']

            #self.log.info('generate_toc: %s' % os.path.join(base_path, toc_file))
            if not self.pargs.dry_run:
                require_dir(base_path)
                with open(os.path.join(base_path, toc_file), 'w') as f:
                    f.write(template.render(**template_data))

        generate_toc(os.path.abspath(self.pargs.output_dir), doc_tree.tree)



app = ManchegoApp('manchego')

if __name__ == '__main__':
    try:
        app.setup()
        app.run()
    finally:
        app.close()