from cement.core import backend, foundation, hook

# set default config options
defaults = backend.defaults('manchego')
defaults['manchego']['output_dir'] = './docs'
defaults['manchego']['from_format'] = 'markdown'
defaults['manchego']['to_format'] = 'rst'

# create an application
app = foundation.CementApp('manchego', config_defaults=defaults,
                           arguments_override_config=True)

try:
    # setup the application
    app.setup()

    # add arguments
    app.args.add_argument('-od', '--outputdir', action='store', dest='output_dir',
                          help='Output path (absolute, or relative to current dir)')
    app.args.add_argument('-f', '--from', action='store', dest='from_format',
                          help='Format of source files, to convert from')
    app.args.add_argument('-t', '--to', action='store', dest='to_format',
                          help='Format of destination files, to convert to')
    app.args.add_argument('input_dir', action='store',
                          help='Path to root dir of source files')
    app.run()

    app.log.info("input_dir: %s" % app.pargs.input_dir)
    app.log.info("output_dir: %s" % app.config.get('manchego', 'output_dir'))
    app.log.info("from_format: %s" % app.config.get('manchego', 'from_format'))
    app.log.info("to_format: %s" % app.config.get('manchego', 'to_format'))

    import pypandoc
    #output = pypandoc.convert('somefile.md', 'rst')

finally:
    # close the application
    app.close()