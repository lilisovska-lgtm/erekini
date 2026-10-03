"""Compile downloaded official Schematron locally; no invoice data involved."""
from pathlib import Path
from saxonche import PySaxonProcessor
p=Path(__file__).parent/'vendor'
with PySaxonProcessor(license=False) as proc:
    xslt=proc.new_xslt30_processor()
    for name in ('cen','peppol'):
        source=p/(name+'.sch')
        for i,style in enumerate(('iso_dsdl_include.xsl','iso_abstract_expand.xsl','iso_svrl_for_xslt2.xsl')):
            out=p/(name+('.xslt' if i==2 else f'-{i}.xml'))
            xslt.transform_to_file(source_file=str(source),stylesheet_file=str(p/style),output_file=str(out))
            source=out
        print('Compiled',name)
