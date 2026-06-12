-- Forked from  https://www.tubefeeder.de/wiki/mpv-touch-controlls.html

require 'mp.options'


-- Create a file ~/.config/mpv/scripts-opt/touchscreen-seek.conf
-- And paste the following content into that file:
-- step = 5

local options = {
    step = 5,
}

read_options(options,'touchscreen-seek')

function touch_seek()
    local pos = get_mouse_area()
    local step = options.step
    if pos == 'left' then
        mp.commandv('seek', -1*step)
    elseif pos == 'right' then
        mp.commandv('seek', step)
    elseif pos == 'center' then
        toggle_pause()
    elseif pos == 'top' then
        toggle_fullscreen()
    end
end

function get_mouse_area()
    local mouse_x, mouse_y = mp.get_mouse_pos()
    local full_w, full_h = mp.get_property('osd-width'), mp.get_property('osd-height')
    local grid_w, grid_h = full_w / 3, full_h / 3
    if mouse_y < grid_h then
        if mouse_x < grid_w then return 'topLeft'
        elseif mouse_x < grid_w * 2 then return 'top'
        else return 'topRight'
        end
    elseif mouse_y < grid_h * 2 then
        if mouse_x < grid_w then return 'left'
        elseif mouse_x < grid_w * 2 then return 'center'
        else return 'right'
        end
    else
        if mouse_x < grid_w then return 'bottomLeft'
        elseif mouse_x < grid_w * 2 then return 'bottom'
        else return 'bottomRight'
        end
    end
end

function toggle_fullscreen()
    local screen_stat = mp.get_property('fullscreen')

    if screen_stat == 'yes' then
        screen_stat = 'no'
    else
        screen_stat = 'yes'
    end

    mp.set_property('fullscreen', screen_stat)
end

function toggle_pause()
    local pause = mp.get_property_native("pause")
    mp.set_property_native("pause", not pause)
end


mp.add_key_binding(nil, "touchscreen-seek", touch_seek)
mp.msg.info("[scripts] Loaded touchscreen-seek Lua flavor")
