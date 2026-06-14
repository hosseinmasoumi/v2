# Generated manually because the local environment is missing grappelli.

import django.db.models.deletion
import django_jalali.db.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('experiment', '0017_alter_experimentsubtype_options_and_more'),
        ('project', '0018_make_technical_fields_nullable'),
    ]

    operations = [
        migrations.CreateModel(
            name='QualityCommission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('layer', models.CharField(choices=[('ASPHALT', 'آسفالت گرم'), ('BASE', 'اساس'), ('SUBBASE', 'زیراساس'), ('EMBANKMENT', 'خاکریزی')], max_length=20, verbose_name='لایه')),
                ('coefficient', models.DecimalField(decimal_places=2, max_digits=6, verbose_name='کمیسیون کیفیت')),
                ('start_kilometer', models.DecimalField(decimal_places=3, max_digits=20, verbose_name='کیلومتر شروع')),
                ('end_kilometer', models.DecimalField(decimal_places=3, max_digits=20, verbose_name='کیلومتر پایان')),
                ('calculation_date', django_jalali.db.models.jDateField(verbose_name='تاریخ محاسبه')),
                ('description', models.TextField(blank=True, null=True, verbose_name='توضیحات')),
                ('created_at', django_jalali.db.models.jDateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='project.project', verbose_name='پروژه')),
            ],
            options={
                'verbose_name': 'کمیسیون کیفیت',
                'verbose_name_plural': 'کمیسیون‌های کیفیت',
                'ordering': ['-created_at'],
            },
        ),
    ]
