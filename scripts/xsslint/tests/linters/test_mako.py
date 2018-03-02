# -*- coding: utf-8 -*-
"""
Tests for linters.py
"""
import textwrap

from ddt import data, ddt

from xsslint.linters.mako import MakoTemplateLinter
from xsslint.linters.python import PythonLinter
from xsslint.reporting import FileResults
from xsslint.rules import Rules
from xsslint.utils import ParseString

from . import TestLinter
from .test_javascript import _build_javascript_linter


def _build_mako_linter():
    return MakoTemplateLinter(
        javascript_linter=_build_javascript_linter(),
        python_linter=PythonLinter(),
    )


@ddt
class TestMakoTemplateLinter(TestLinter):
    """
    Test MakoTemplateLinter
    """

    @data(
        {'directory': 'lms/templates', 'expected': True},
        {'directory': 'lms/templates/support', 'expected': True},
        {'directory': 'lms/templates/support', 'expected': True},
        {'directory': 'test_root/staticfiles/templates', 'expected': False},
        {'directory': './test_root/staticfiles/templates', 'expected': False},
        {'directory': './some/random/path', 'expected': False},
    )
    def test_is_valid_directory(self, data):
        """
        Test _is_valid_directory correctly determines mako directories
        """
        linter = _build_mako_linter()
        linter._skip_mako_dirs = ('test_root',)

        self.assertEqual(linter._is_valid_directory(data['directory']), data['expected'])

    @data(
        {
            'template': '\n <%page expression_filter="h"/>',
            'rule': None
        },
        {
            'template':
                '\n <%page args="section_data" expression_filter="h" /> ',
            'rule': None
        },
        {
            'template': '\n ## <%page expression_filter="h"/>',
            'rule': Rules.mako_missing_default
        },
        {
            'template':
                '\n <%page expression_filter="h" /> '
                '\n <%page args="section_data"/>',
            'rule': Rules.mako_multiple_page_tags
        },
        {
            'template':
                '\n <%page expression_filter="h" /> '
                '\n ## <%page args="section_data"/>',
            'rule': None
        },
        {
            'template': '\n <%page args="section_data" /> ',
            'rule': Rules.mako_missing_default
        },
        {
            'template':
                '\n <%page args="section_data"/> <some-other-tag expression_filter="h" /> ',
            'rule': Rules.mako_missing_default
        },
        {
            'template': '\n',
            'rule': Rules.mako_missing_default
        },
    )
    def test_check_page_default(self, data):
        """
        Test _check_mako_file_is_safe with different page defaults
        """
        linter = _build_mako_linter()
        results = FileResults('')

        linter._check_mako_file_is_safe(data['template'], results)

        num_violations = 0 if data['rule'] is None else 1
        self.assertEqual(len(results.violations), num_violations)
        if num_violations > 0:
            self.assertEqual(results.violations[0].rule, data['rule'])

    @data(
        {'expression': '${x}', 'rule': None},
        {'expression': '${{unbalanced}', 'rule': Rules.mako_unparseable_expression},
        {'expression': '${x | n}', 'rule': Rules.mako_invalid_html_filter},
        {'expression': '${x | n, decode.utf8}', 'rule': None},
        {'expression': '${x | h}', 'rule': Rules.mako_unwanted_html_filter},
        {'expression': '  ## ${commented_out | h}', 'rule': None},
        {'expression': '${x | n, dump_js_escaped_json}', 'rule': Rules.mako_invalid_html_filter},
    )
    def test_check_mako_expressions_in_html(self, data):
        """
        Test _check_mako_file_is_safe in html context provides appropriate violations
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = textwrap.dedent("""
            <%page expression_filter="h"/>
            {expression}
        """.format(expression=data['expression']))

        linter._check_mako_file_is_safe(mako_template, results)

        self._validate_data_rules(data, results)

    def test_check_mako_expression_display_name(self):
        """
        Test _check_mako_file_is_safe with display_name_with_default_escaped
        fails.
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = textwrap.dedent("""
            <%page expression_filter="h"/>
            ${course.display_name_with_default_escaped}
        """)

        linter._check_mako_file_is_safe(mako_template, results)

        self.assertEqual(len(results.violations), 1)
        self.assertEqual(results.violations[0].rule, Rules.python_deprecated_display_name)

    @data(
        {
            # Python blocks between <% ... %> use the same Python linting as
            # Mako expressions between ${ ... }. This single test verifies
            # that these blocks are linted. The individual linting rules are
            # tested in the Mako expression tests that follow.
            'expression':
                textwrap.dedent("""
                    <%
                        a_link_start = '<a class="link-courseURL" rel="external" href="'
                        a_link_end = '">' + _("your course summary page") + '</a>'
                        a_link = a_link_start + lms_link_for_about_page + a_link_end
                        text = _("Introductions, prerequisites, FAQs that are used on %s (formatted in HTML)") % a_link
                    %>
                """),
            'rule': [Rules.python_wrap_html, Rules.python_concat_html, Rules.python_wrap_html]
        },
        {
            'expression':
                textwrap.dedent("""
                    ${"Mixed {span_start}text{span_end}".format(
                        span_start=HTML("<span>"),
                        span_end=HTML("</span>"),
                    )}
                """),
            'rule': Rules.python_requires_html_or_text
        },
        {
            'expression':
                textwrap.dedent("""
                    ${Text("Mixed {span_start}text{span_end}").format(
                        span_start=HTML("<span>"),
                        span_end=HTML("</span>"),
                    )}
                """),
            'rule': None
        },
        {
            'expression':
                textwrap.dedent("""
                    ${"Mixed {span_start}{text}{span_end}".format(
                        span_start=HTML("<span>"),
                        text=Text("This should still break."),
                        span_end=HTML("</span>"),
                    )}
                """),
            'rule': Rules.python_requires_html_or_text
        },
        {
            'expression':
                textwrap.dedent("""
                    ${Text("Mixed {link_start}text{link_end}".format(
                        link_start=HTML("<a href='{}'>").format(url),
                        link_end=HTML("</a>"),
                    ))}
                """),
            'rule': [Rules.python_close_before_format, Rules.python_requires_html_or_text]
        },
        {
            'expression':
                textwrap.dedent("""
                    ${Text("Mixed {link_start}text{link_end}").format(
                        link_start=HTML("<a href='{}'>".format(url)),
                        link_end=HTML("</a>"),
                    )}
                """),
            'rule': Rules.python_close_before_format
        },
        {
            'expression':
                textwrap.dedent("""
                    ${"Mixed {span_start}text{span_end}".format(
                        span_start="<span>",
                        span_end="</span>",
                    )}
                """),
            'rule': [Rules.python_wrap_html, Rules.python_wrap_html]
        },
        {
            'expression':
                textwrap.dedent("""
                    ${Text(_("String with multiple lines "
                        "{link_start}unenroll{link_end} "
                        "and final line")).format(
                            link_start=HTML(
                                '<a id="link__over_multiple_lines" '
                                'data-course-id="{course_id}" '
                                'href="#test-modal">'
                            ).format(
                                course_id=course_overview.id
                            ),
                            link_end=HTML('</a>'),
                    )}
                """),
            'rule': None
        },
        {
            'expression': "${'<span></span>'}",
            'rule': Rules.python_wrap_html
        },
        {
            'expression': "${'Embedded HTML <strong></strong>'}",
            'rule': Rules.python_wrap_html
        },
        {
            'expression': "${ HTML('<span></span>') }",
            'rule': None
        },
        {
            'expression': "${HTML(render_entry(map['entries'], child))}",
            'rule': None
        },
        {
            'expression': "${ '<span></span>' + 'some other text' }",
            'rule': [Rules.python_concat_html, Rules.python_wrap_html]
        },
        {
            'expression': "${ HTML('<span>missing closing parentheses.</span>' }",
            'rule': Rules.python_parse_error
        },
        {
            'expression': "${'Rock &amp; Roll'}",
            'rule': Rules.mako_html_entities
        },
        {
            'expression': "${'Rock &#38; Roll'}",
            'rule': Rules.mako_html_entities
        },
    )
    def test_check_mako_with_text_and_html(self, data):
        """
        Test _check_mako_file_is_safe tests for proper use of Text() and Html().
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = textwrap.dedent("""
            <%page expression_filter="h"/>
            {expression}
        """.format(expression=data['expression']))

        linter._check_mako_file_is_safe(mako_template, results)

        self._validate_data_rules(data, results)

    def test_check_mako_entity_with_no_default(self):
        """
        Test _check_mako_file_is_safe does not fail on entities when
        safe-by-default is not set.
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = "${'Rock &#38; Roll'}"

        linter._check_mako_file_is_safe(mako_template, results)

        self.assertEqual(len(results.violations), 1)
        self.assertEqual(results.violations[0].rule, Rules.mako_missing_default)

    def test_check_mako_expression_default_disabled(self):
        """
        Test _check_mako_file_is_safe with disable pragma for safe-by-default
        works to designate that this is not a Mako file
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = textwrap.dedent("""
            # This is anything but a Mako file.

            # pragma can appear anywhere in file
            # xss-lint: disable=mako-missing-default
        """)

        linter._check_mako_file_is_safe(mako_template, results)

        self.assertEqual(len(results.violations), 1)
        self.assertTrue(results.violations[0].is_disabled)

    def test_check_mako_expression_disabled(self):
        """
        Test _check_mako_file_is_safe with disable pragma results in no
        violation
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = textwrap.dedent("""
            <%page expression_filter="h"/>
            ## xss-lint: disable=mako-unwanted-html-filter
            ${x | h}
        """)

        linter._check_mako_file_is_safe(mako_template, results)

        self.assertEqual(len(results.violations), 1)
        self.assertTrue(results.violations[0].is_disabled)

    @data(
        {'template': '{% extends "wiki/base.html" %}'},
        {'template': '{{ message }}'},
        {'template': '{# comment #}'},
    )
    def test_check_mako_on_django_template(self, data):
        """
        Test _check_mako_file_is_safe with disable pragma results in no
        violation
        """
        linter = _build_mako_linter()
        results = FileResults('')

        linter._check_mako_file_is_safe(data['template'], results)

        self.assertEqual(len(results.violations), 0)

    def test_check_mako_expressions_in_html_with_escape_filter(self):
        """
        Test _check_mako_file_is_safe results in no violations,
        when strip_all_tags_but_br filter is applied in html context
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = textwrap.dedent("""
            <%page expression_filter="h"/>
            ${x | n, strip_all_tags_but_br}
        """)

        linter._check_mako_file_is_safe(mako_template, results)
        self.assertEqual(len(results.violations), 0)

    def test_check_mako_expressions_in_html_without_default(self):
        """
        Test _check_mako_file_is_safe in html context without the page level
        default h filter suppresses expression level violation
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = textwrap.dedent("""
            ${x | h}
        """)

        linter._check_mako_file_is_safe(mako_template, results)

        self.assertEqual(len(results.violations), 1)
        self.assertEqual(results.violations[0].rule, Rules.mako_missing_default)

    @data(
        {'expression': '${x}', 'rule': Rules.mako_invalid_js_filter},
        {'expression': '${{unbalanced}', 'rule': Rules.mako_unparseable_expression},
        {'expression': '${x | n}', 'rule': Rules.mako_invalid_js_filter},
        {'expression': '${x | h}', 'rule': Rules.mako_invalid_js_filter},
        {'expression': '${x | n, dump_js_escaped_json}', 'rule': None},
        {'expression': '${x | n, decode.utf8}', 'rule': None},
    )
    def test_check_mako_expressions_in_javascript(self, data):
        """
        Test _check_mako_file_is_safe in JavaScript script context provides
        appropriate violations
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = textwrap.dedent("""
            <%page expression_filter="h"/>
            ## switch to JavaScript context
            <script>
                {expression}
            </script>
            ## switch back to HTML context
            ${{x}}
        """.format(expression=data['expression']))

        linter._check_mako_file_is_safe(mako_template, results)

        self._validate_data_rules(data, results)

    @data(
        {'expression': '${x}', 'rule': Rules.mako_invalid_js_filter},
        {'expression': '"${x | n, js_escaped_string}"', 'rule': None},
    )
    def test_check_mako_expressions_in_require_module(self, data):
        """
        Test _check_mako_file_is_safe in JavaScript require context provides
        appropriate violations
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = textwrap.dedent("""
            <%page expression_filter="h"/>
            ## switch to JavaScript context (after next line)
            <%static:require_module module_name="${{x}}" class_name="TestFactory">
                {expression}
            </%static:require_module>
            ## switch back to HTML context
            ${{x}}
        """.format(expression=data['expression']))

        linter._check_mako_file_is_safe(mako_template, results)

        self._validate_data_rules(data, results)

    @data(
        {'expression': '${x}', 'rule': Rules.mako_invalid_js_filter},
        {'expression': '"${x | n, js_escaped_string}"', 'rule': None},
    )
    def test_check_mako_expressions_in_require_js(self, data):
        """
        Test _check_mako_file_is_safe in JavaScript require js context provides
        appropriate violations
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = textwrap.dedent("""
            <%page expression_filter="h"/>
            # switch to JavaScript context
            <%block name="requirejs">
                {expression}
            </%block>
            ## switch back to HTML context
            ${{x}}
        """.format(expression=data['expression']))

        linter._check_mako_file_is_safe(mako_template, results)

        self._validate_data_rules(data, results)

    @data(
        {'media_type': 'text/javascript', 'rule': None},
        {'media_type': 'text/ecmascript', 'rule': None},
        {'media_type': 'application/ecmascript', 'rule': None},
        {'media_type': 'application/javascript', 'rule': None},
        {'media_type': 'text/x-mathjax-config', 'rule': None},
        {'media_type': 'json/xblock-args', 'rule': None},
        {'media_type': 'text/template', 'rule': Rules.mako_invalid_html_filter},
        {'media_type': 'unknown/type', 'rule': Rules.mako_unknown_context},
    )
    def test_check_mako_expressions_in_script_type(self, data):
        """
        Test _check_mako_file_is_safe in script tag with different media types
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = textwrap.dedent("""
            <%page expression_filter="h"/>
            # switch to JavaScript context
            <script type="{}">
                ${{x | n, dump_js_escaped_json}}
            </script>
            ## switch back to HTML context
            ${{x}}
        """).format(data['media_type'])

        linter._check_mako_file_is_safe(mako_template, results)

        self._validate_data_rules(data, results)

    def test_check_mako_expressions_in_mixed_contexts(self):
        """
        Test _check_mako_file_is_safe in mixed contexts provides
        appropriate violations
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = textwrap.dedent("""
            <%page expression_filter="h"/>
            ${x | h}
            <script type="text/javascript">
                ${x | h}
            </script>
            ${x | h}
            <%static:require_module module_name="${x}" class_name="TestFactory">
                ${x | h}
            </%static:require_module>
            ${x | h}
            <%static:studiofrontend page="${x}">
                ${x | h}
            </%static:studiofrontend>
            ${x | h}
        """)

        linter._check_mako_file_is_safe(mako_template, results)

        self.assertEqual(len(results.violations), 7)
        self.assertEqual(results.violations[0].rule, Rules.mako_unwanted_html_filter)
        self.assertEqual(results.violations[1].rule, Rules.mako_invalid_js_filter)
        self.assertEqual(results.violations[2].rule, Rules.mako_unwanted_html_filter)
        self.assertEqual(results.violations[3].rule, Rules.mako_invalid_js_filter)
        self.assertEqual(results.violations[4].rule, Rules.mako_unwanted_html_filter)
        self.assertEqual(results.violations[5].rule, Rules.mako_invalid_js_filter)
        self.assertEqual(results.violations[6].rule, Rules.mako_unwanted_html_filter)

    def test_check_mako_expressions_javascript_strings(self):
        """
        Test _check_mako_file_is_safe javascript string specific rules.
        - mako_js_missing_quotes
        - mako_js_html_string
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = textwrap.dedent("""
            <%page expression_filter="h"/>
            <script type="text/javascript">
                var valid1 = '${x | n, js_escaped_string} ${y | n, js_escaped_string}'
                var valid2 = '${x | n, js_escaped_string} ${y | n, js_escaped_string}'
                var valid3 = 'string' + ' ${x | n, js_escaped_string} '
                var valid4 = "${Text(_('Some mixed text{begin_span}with html{end_span}')).format(
                    begin_span=HTML('<span>'),
                    end_span=HTML('</span>'),
                ) | n, js_escaped_string}"
                var valid5 = " " + "${Text(_('Please {link_start}send us e-mail{link_end}.')).format(
                    link_start=HTML('<a href="#" id="feedback_email">'),
                    link_end=HTML('</a>'),
                ) | n, js_escaped_string}";
                var invalid1 = ${x | n, js_escaped_string};
                var invalid2 = '<strong>${x | n, js_escaped_string}</strong>'
                var invalid3 = '<strong>${x | n, dump_js_escaped_json}</strong>'
            </script>
        """)

        linter._check_mako_file_is_safe(mako_template, results)

        self.assertEqual(len(results.violations), 3)
        self.assertEqual(results.violations[0].rule, Rules.mako_js_missing_quotes)
        self.assertEqual(results.violations[1].rule, Rules.mako_js_html_string)
        self.assertEqual(results.violations[2].rule, Rules.mako_js_html_string)

    def test_check_javascript_in_mako_javascript_context(self):
        """
        Test _check_mako_file_is_safe with JavaScript error in JavaScript
        context.
        """
        linter = _build_mako_linter()
        results = FileResults('')

        mako_template = textwrap.dedent("""
            <%page expression_filter="h"/>
            <script type="text/javascript">
                var message = '<p>' + msg + '</p>';
            </script>
        """)

        linter._check_mako_file_is_safe(mako_template, results)

        self.assertEqual(len(results.violations), 1)
        self.assertEqual(results.violations[0].rule, Rules.javascript_concat_html)
        self.assertEqual(results.violations[0].start_line, 4)

    @data(
        {'template': "\n${x | n}", 'parseable': True},
        {
            'template': textwrap.dedent(
                """
                    <div>${(
                        'tabbed-multi-line-expression'
                    ) | n}</div>
                """),
            'parseable': True
        },
        {'template': "${{unparseable}", 'parseable': False},
    )
    def test_expression_detailed_results(self, data):
        """
        Test _check_mako_file_is_safe provides detailed results, including line
        numbers, columns, and line
        """
        linter = _build_mako_linter()
        results = FileResults('')

        linter._check_mako_file_is_safe(data['template'], results)

        self.assertEqual(len(results.violations), 2)
        self.assertEqual(results.violations[0].rule, Rules.mako_missing_default)

        violation = results.violations[1]
        lines = list(data['template'].splitlines())
        self.assertTrue("${" in lines[violation.start_line - 1])
        self.assertTrue(lines[violation.start_line - 1].startswith("${", violation.start_column - 1))
        if data['parseable']:
            self.assertTrue("}" in lines[violation.end_line - 1])
            self.assertTrue(lines[violation.end_line - 1].startswith("}", violation.end_column - len("}") - 1))
        else:
            self.assertEqual(violation.start_line, violation.end_line)
            self.assertEqual(violation.end_column, "?")
        self.assertEqual(len(violation.lines), violation.end_line - violation.start_line + 1)
        for line_index in range(0, len(violation.lines)):
            self.assertEqual(violation.lines[line_index], lines[line_index + violation.start_line - 1])

    @data(
        {'template': "${x}"},
        {'template': "\n ${x}"},
        {'template': "${x} "},
        {'template': "${{test-balanced-delims}} "},
        {'template': "${'{unbalanced in string'}"},
        {'template': "${'unbalanced in string}'}"},
        {'template': "${(\n    'tabbed-multi-line-expression'\n  )}"},
    )
    def test_find_mako_expressions(self, data):
        """
        Test _find_mako_expressions for parseable expressions
        """
        linter = _build_mako_linter()

        expressions = linter._find_mako_expressions(data['template'])

        self.assertEqual(len(expressions), 1)
        start_index = expressions[0].start_index
        end_index = expressions[0].end_index
        self.assertEqual(data['template'][start_index:end_index], data['template'].strip())
        self.assertEqual(expressions[0].expression, data['template'].strip())

    @data(
        {'template': " ${{unparseable} ${}", 'start_index': 1},
        {'template': " ${'unparseable} ${}", 'start_index': 1},
    )
    def test_find_unparseable_mako_expressions(self, data):
        """
        Test _find_mako_expressions for unparseable expressions
        """
        linter = _build_mako_linter()

        expressions = linter._find_mako_expressions(data['template'])
        self.assertTrue(2 <= len(expressions))
        self.assertEqual(expressions[0].start_index, data['start_index'])
        self.assertIsNone(expressions[0].expression)

    @data(
        {
            'template': '${""}',
            'result': {'start_index': 2, 'end_index': 4, 'quote_length': 1}
        },
        {
            'template': "${''}",
            'result': {'start_index': 2, 'end_index': 4, 'quote_length': 1}
        },
        {
            'template': "${'Hello'}",
            'result': {'start_index': 2, 'end_index': 9, 'quote_length': 1}
        },
        {
            'template': '${""" triple """}',
            'result': {'start_index': 2, 'end_index': 16, 'quote_length': 3}
        },
        {
            'template': r""" ${" \" \\"} """,
            'result': {'start_index': 3, 'end_index': 11, 'quote_length': 1}
        },
        {
            'template': "${'broken string}",
            'result': {'start_index': 2, 'end_index': None, 'quote_length': None}
        },
    )
    def test_parse_string(self, data):
        """
        Test _parse_string helper
        """
        linter = _build_mako_linter()

        parse_string = ParseString(data['template'], data['result']['start_index'], len(data['template']))
        string_dict = {
            'start_index': parse_string.start_index,
            'end_index': parse_string.end_index,
            'quote_length': parse_string.quote_length,
        }

        self.assertDictEqual(string_dict, data['result'])
        if parse_string.end_index is not None:
            self.assertEqual(data['template'][parse_string.start_index:parse_string.end_index], parse_string.string)
            start_inner_index = parse_string.start_index + parse_string.quote_length
            end_inner_index = parse_string.end_index - parse_string.quote_length
            self.assertEqual(data['template'][start_inner_index:end_inner_index], parse_string.string_inner)