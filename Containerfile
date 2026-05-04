FROM docker.io/library/nginx:alpine

# Mirrors the GitHub Pages staging in .github/workflows/pages.yml:
#   /              -> site/ (landing page)
#   /costco-gas/   -> costco_gas/pwa/ (PWA + data/)
COPY site/ /usr/share/nginx/html/
COPY costco_gas/pwa/ /usr/share/nginx/html/costco-gas/

# Make nginx listen on 8080 so -p 8080:8080 works without a host privileged port.
# Use POSIX [[:space:]] (BusyBox sed in Alpine doesn't support \s).
RUN sed -i 's/listen[[:space:]]\{1,\}80;/listen 8080;/' /etc/nginx/conf.d/default.conf \
    && grep -q 'listen 8080;' /etc/nginx/conf.d/default.conf
EXPOSE 8080

# podman build -t costco-gas -f Containerfile .
# podman run -d -p 8080:8080 --name costco-gas costco-gas


