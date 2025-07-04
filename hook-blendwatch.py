# PyInstaller hook for blendwatch
# This ensures all necessary modules are included

hiddenimports = [
    # Click dependencies
    'click',
    'click.core',
    'click.decorators',
    'click.exceptions',
    'click.parser',
    'click.types',
    'click.utils',
    'click.termui',
    'click.testing',
    
    # Colorama
    'colorama',
    'colorama.ansi',
    'colorama.ansitowin32',
    'colorama.initialise',
    'colorama.win32',
    'colorama.winterm',
    
    # Watchdog
    'watchdog',
    'watchdog.observers',
    'watchdog.observers.api',
    'watchdog.observers.polling',
    'watchdog.events',
    'watchdog.utils',
    'watchdog.utils.dirsnapshot',
    
    # TOML libraries
    'tomli',
    'tomli._parser',
    'tomli._re',
    
    # zstandard
    'zstandard',
    
    # blender-asset-tracer
    'blender_asset_tracer',
    'blender_asset_tracer.cli',
    'blender_asset_tracer.cli.common',
    'blender_asset_tracer.bpathlib',
    'blender_asset_tracer.trace',
    'blender_asset_tracer.trace.dependencies',
    'blender_asset_tracer.trace.progress',
    'blender_asset_tracer.blendfile',
    'blender_asset_tracer.blendfile.dna',
    'blender_asset_tracer.blendfile.dna_io',
    'blender_asset_tracer.blendfile.exceptions',
    'blender_asset_tracer.blendfile.header',
    'blender_asset_tracer.blendfile.iterators',
    'blender_asset_tracer.blendfile.magic_compression',
]

# Ensure TOML config files are included
datas = [
    ('src/blendwatch/default.config.toml', 'blendwatch/'),
]
