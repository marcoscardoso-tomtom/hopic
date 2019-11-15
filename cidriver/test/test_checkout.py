# Copyright (c) 2019 - 2019 TomTom N.V. (https://tomtom.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function
from ..cli import cli

from click.testing import CliRunner
import git
import os
from pathlib import Path
import pytest
import sys


_source_date_epoch = 7 * 24 * 3600
_git_time = '{} +0000'.format(_source_date_epoch)


def run(*args, env=None):
    runner = CliRunner(mix_stderr=False, env=env)
    with runner.isolated_filesystem():
        for arg in args:
            result = runner.invoke(cli, arg)

            if result.stdout_bytes:
                print(result.stdout, end='')
            if result.stderr_bytes:
                print(result.stderr, end='', file=sys.stderr)

            if result.exception is not None and not isinstance(result.exception, SystemExit):
                raise result.exception
            
            if result.exit_code != 0:
                return result

    return result


def test_clean_submodule_checkout(capfd, tmp_path):
    author = git.Actor('Bob Tester', 'bob@example.net')
    commitargs = dict(
            author_date=_git_time,
            commit_date=_git_time,
            author=author,
            committer=author,
        )

    dummy_content = 'Lalalala!\n'
    subrepo = tmp_path / 'subrepo'
    with git.Repo.init(str(subrepo), expand_vars=False) as repo:
        with (subrepo / 'dummy.txt').open('w') as f:
            f.write(dummy_content)
        repo.index.add(('dummy.txt',))
        repo.index.commit(message='Initial dummy commit', **commitargs)

    toprepo = tmp_path / 'repo'
    with git.Repo.init(str(toprepo), expand_vars=False) as repo:
        with (toprepo / 'hopic-ci-config.yaml').open('w') as f:
            f.write('''\
phases:
  build:
    test:
      - cat subrepo/dummy.txt
''')
        repo.index.add(('hopic-ci-config.yaml',))
        repo.git.submodule(('add', '../subrepo', 'subrepo'))
        repo.index.commit(message='Initial commit', **commitargs)

    # Successful checkout and build
    result = run(
            ('checkout-source-tree', '--clean', '--target-remote', str(toprepo), '--target-ref', 'master'),
            ('build',),
        )
    assert result.exit_code == 0
    out, err = capfd.readouterr()
    build_out = ''.join(out.splitlines(keepends=True)[1:])
    assert build_out == dummy_content

    # Make submodule checkout fail
    subrepo.rename(subrepo.parent / 'old-subrepo')

    # Expected failure
    with pytest.raises(git.GitCommandError, match=r'(?is)submodule.*repository.*\bdoes not exist\b'):
        result = run(('checkout-source-tree', '--clean', '--target-remote', str(toprepo), '--target-ref', 'master'))

    # Ignore submodule failure only
    result = run(('checkout-source-tree', '--clean', '--ignore-initial-submodule-checkout-failure', '--target-remote', str(toprepo), '--target-ref', 'master'))
    assert result.exit_code == 0


def test_default_clean_checkout_option(capfd, tmp_path):
    author = git.Actor('Bob Tester', 'bob@example.net')
    commitargs = dict(
        author_date=_git_time,
        commit_date=_git_time,
        author=author,
        committer=author,
    )

    toprepo = tmp_path / 'repo'
    with git.Repo.init(str(toprepo), expand_vars=False) as repo:
        with (toprepo / 'hopic-ci-config.yaml').open('w') as f:
            f.write('''\
{}
''')
        temp_test_file = 'random_file.txt'
        with (toprepo / temp_test_file).open('w') as f:
            f.write('''\
nothing to see here
''')

        repo.index.add(('hopic-ci-config.yaml',))
        repo.index.commit(message='Initial commit', **commitargs)
        commit = list(repo.iter_commits('master', max_count=1))[0]
        result = run(('--workspace', str(toprepo), 'checkout-source-tree', '--clean', '--target-remote', str(toprepo), '--target-ref', 'master'))
        assert result.exit_code == 0
        assert not (toprepo / temp_test_file).is_file()
        assert commit.committed_date == (toprepo / 'hopic-ci-config.yaml').stat().st_mtime
