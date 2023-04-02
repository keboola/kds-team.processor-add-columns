import csv
import glob
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from keboola.component import ComponentBase, UserException
# configuration variables
from keboola.component.dao import TableDefinition

# global constants'
from user_functions import UserFunctions

KEY_COLUMNS = 'columns'
# #### Keep for debug
KEY_DEBUG = 'debug'
MANDATORY_PARS = []


@dataclass
class TableDef:
    path: str
    file_name: str
    is_sliced: bool
    manifest: dict = field(default_factory=dict)


class Component(ComponentBase):

    def __init__(self):
        ComponentBase.__init__(self)
        self.validate_configuration_parameters(MANDATORY_PARS)
        # initialize instance parameters
        self.user_functions = UserFunctions()

    def run(self):
        tables = self.get_input_tables_definitions()
        columns = self.configuration.parameters[KEY_COLUMNS]
        for t in tables:
            for c in columns:
                self.add_column(t, c)

        # move files
        if os.path.exists(self.files_in_path):
            shutil.copytree(self.files_in_path, self.files_out_path, dirs_exist_ok=True)

    def add_column(self, t: TableDefinition, column_def: dict):

        column_value = self._perform_custom_function(column_def["function"])
        column_name = column_def["name"]

        if t.is_sliced:
            # is sliced header-less files in a folder
            self.add_column_to_manifest_and_copy_to_out(t.full_path, t._raw_manifest, column_name)  # noqa
            # add columns in slices
            all_slices = glob.glob(t.full_path + '/*')
            for slice_file in all_slices:
                self._add_column_to_file(slice_file, t.delimiter, t.enclosure, column_value, column_name,
                                         write_header=False)

        elif t.columns:
            # does not have header in file
            self.add_column_to_manifest_and_copy_to_out(t.full_path, t._raw_manifest, column_name)  # noqa
            self._add_column_to_file(t.full_path, t.delimiter, t.enclosure, column_value, column_name,
                                     write_header=False)
        else:
            self._add_column_to_file(t.full_path, t.delimiter, t.enclosure, column_value, column_name,
                                     write_header=True)
            self._copy_manifest_to_out(t)

    def _add_column_to_file(self, file_path: str, delimiter, enclosure, column_value, column_name,
                            write_header: bool = False):

        new_path = file_path.replace(self.tables_in_path, self.tables_out_path)
        Path(new_path).parent.mkdir(exist_ok=True)
        with open(file_path, encoding='utf-8') as from_file, open(new_path, mode="w", encoding='utf-8') as to_file:
            delimiter = delimiter
            enclosure = enclosure
            reader = csv.reader(from_file, lineterminator='\n', delimiter=delimiter, quotechar=enclosure)
            writer = csv.writer(to_file, lineterminator='\n', delimiter=delimiter, quotechar=enclosure)

            first_line = next(reader)
            if write_header:
                first_line.append(column_name)
                writer.writerow(first_line)

            for r in reader:
                r.append(column_value)
                writer.writerow(r)

    def _copy_manifest_to_out(self, t: TableDefinition):
        if t.get_manifest_dictionary():
            new_path = os.path.join(self.tables_out_path, Path(t.full_path).name + '.manifest')
            shutil.copy(t.full_path + '.manifest', new_path)

    def add_column_to_manifest_and_copy_to_out(self, file_path, manifest, new_column):
        manifest['columns'].append(new_column)
        with open(os.path.join(self.tables_out_path, Path(file_path).name + '.manifest'), 'w+') as out_f:
            json.dump(manifest, out_f)

    def _copy_table_to_out(self, t: TableDefinition):
        if Path(t.full_path).is_dir():
            shutil.copytree(t.full_path, Path(self.tables_out_path).joinpath(t.name))
        else:
            shutil.copy(t.full_path, Path(self.tables_out_path).joinpath(t.name))

    def _perform_custom_function(self, function_cfg):

        if not function_cfg.get('function'):
            raise ValueError(
                F'The function value is object and is not a valid function object: {function_cfg}')
        new_args = []
        for arg in function_cfg.get('args'):
            if isinstance(arg, dict):
                arg = self._perform_custom_function(arg)
            new_args.append(arg)
        function_cfg['args'] = new_args

        return self.user_functions.execute_function(function_cfg['function'], *function_cfg.get('args'))


"""
        Main entrypoint
"""
if __name__ == "__main__":
    try:
        comp = Component()
        # this triggers the run method by default and is controlled by the configuration.action parameter
        comp.execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)
