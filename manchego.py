import copy
import errno
import fnmatch
import glob
import os
import pypandoc

from cement.core import controller, foundation, backend
from collections import defaultdict


def find_files(directory, pattern, ignore_names=[], ignore_paths=[]):
    for root, dirs, files in os.walk(directory):
        if root in ignore_paths:
            continue
        for basename in files:
            if basename not in ignore_names and fnmatch.fnmatch(basename, pattern):
                filename = os.path.join(root, basename)
                yield (os.path.abspath(root), filename)

def require_dir(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise

def get_doc_title(doc_file, default="untitled"):
    title = doc_file.readline().strip()
    if not title.startswith('% '):
        return default
    return re.sub(r'^%\s+', '', title)

FILE_EXTENSIONS = {
    'rst': 'rst',
    'markdown': 'md',
    # etc
}

class ManchegoApp(foundation.CementApp):
    _defaults = {
        'manchego': {
            'file_pattern': '*.md',
            'toc_file': 'index.md',
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

        contents = defaultdict(list)
        basepath = os.path.abspath(self.pargs.input_dir)
        # convert existing docs and save to output_dir
        for path,filename in find_files(self.pargs.input_dir, file_pattern):

            path_stub = path[len(basepath)+1:]# eg 'kitchen/cookbooks/xxx' (not a full relative or absolute path)
            output_subdir = os.path.join(output_dir, path_stub)
            require_dir(output_subdir)# create the dir if not exists

            output_path = "%s.%s" % (os.path.splitext(os.path.join(output_subdir, os.path.basename(filename)))[0],
                                     FILE_EXTENSIONS[to_format])
            contents[path_stub].append(
                (filename, output_path, os.path.basename(filename))
            )

            with open(output_path, 'w') as f:
                f.write(pypandoc.convert(filename, to_format, format=from_format))
        
        # generate TOCs for each path in output_dir
        self.log.info(contents)
        for path, files in contents.items():
            if len(files) == 1:
                # no TOC needed, link directly
                pass
            for filename, output_path, basename in files:
                #get_doc_title()
                pass


app = ManchegoApp('manchego')

if __name__ == '__main__':
    try:
        app.setup()
        app.run()
    finally:
        app.close()